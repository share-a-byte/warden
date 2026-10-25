"""Inference for the notebook's autoencoder using the per-feature top-k score.

Needs the files the notebook saves in outputs/: meta.json, scaler.joblib, autoencoder_best.pt.
Usage:
    det = AutoencoderDetector("outputs")
    result = det.score(wide_df)          # wide_df: rows = timestamps, columns = the training feature names, RAW units
    result[result.alert]                 # flagged timesteps, with the features that drove each alert
    result, labels = score_files(det, daily_csv_paths)  # for multiple files: reset windows at each file

The CLI also writes anomaly_rows.csv: original long-format rows for the top
contributing features at alerted timesteps, including source file and data-row number.
"""
import glob
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn



class WindowAutoencoder(nn.Module):                      # same as the notebook ("dense")
    def __init__(self, n_feat, window, hidden, bottleneck, dropout):
        super().__init__()
        n_in = n_feat * window
        self.encoder = nn.Sequential(nn.Linear(n_in, hidden), nn.GELU(), nn.Dropout(dropout),
                                     nn.Linear(hidden, bottleneck))
        self.decoder = nn.Sequential(nn.Linear(bottleneck, hidden), nn.GELU(), nn.Linear(hidden, n_in))

    def forward(self, x):
        return self.decoder(self.encoder(x))


class GRUAutoencoder(nn.Module):                         # same as the notebook ("gru")
    def __init__(self, n_feat, window, hidden, bottleneck, dropout):
        super().__init__()
        self.n_feat, self.window = n_feat, window
        self.enc_gru = nn.GRU(n_feat, hidden, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.to_latent = nn.Linear(hidden, bottleneck)
        self.from_latent = nn.Linear(bottleneck, hidden)
        self.dec_gru = nn.GRU(hidden, hidden, batch_first=True)
        self.out = nn.Linear(hidden, n_feat)

    def forward(self, x):
        b = x.shape[0]
        _, h = self.enc_gru(x.reshape(b, self.window, self.n_feat))
        z = self.to_latent(self.drop(h[-1]))
        dec_in = self.from_latent(z).unsqueeze(1).repeat(1, self.window, 1)
        dec_out, _ = self.dec_gru(dec_in)
        return self.out(dec_out).reshape(b, -1)


def pivot_long(df_long, timestamp_col="simulated_at", value_col="value",
               id_cols=("asset_id", "metric"), facility_col="facility_id"):
    """Long log rows (one per timestamp/asset/metric) -> wide frame with the notebook's feature names."""
    keys = ([facility_col] if facility_col else []) + list(id_cols)
    name = df_long[keys[0]].astype(str)
    for c in keys[1:]:
        name = name + "__" + df_long[c].astype(str)
    t = pd.to_datetime(df_long[timestamp_col], errors="coerce")
    tmp = pd.DataFrame({"t": t, "f": name, "v": df_long[value_col]}).dropna(subset=["t", "v"])
    return tmp.groupby(["t", "f"])["v"].mean().unstack("f").sort_index().astype("float32")


def load_wide(paths, timestamp_col="simulated_at", value_col="value", id_cols=("asset_id", "metric"),
              facility_col="facility_id", label_col="is_attack"):
    """Read long-format chunk files (.csv or .csv.gz), pivot EACH one to wide, then join them in time order.
    Only the needed columns are read, and the big long table is never held in memory at once.
    Returns (wide, labels). labels is a per-timestep 0/1 Series if label_col is in the files, else None."""
    wides, labs = [], []
    for path in paths:
        header = pd.read_csv(path, nrows=0).columns
        use = [timestamp_col, value_col, *id_cols] + ([facility_col] if facility_col else [])
        has_label = bool(label_col) and label_col in header
        if has_label:
            use.append(label_col)
        d = pd.read_csv(path, usecols=use)
        wides.append(pivot_long(d, timestamp_col, value_col, id_cols, facility_col))
        if has_label:
            labs.append(d.groupby(pd.to_datetime(d[timestamp_col], errors="coerce"))[label_col].max())
    wide = pd.concat(wides).groupby(level=0).mean().sort_index()        # mean() only matters if chunks overlap in time
    labels = pd.concat(labs).groupby(level=0).max().sort_index() if labs else None
    return wide, labels


def evaluate(detector, result, labels):
    """Score quality against known attack labels. Use on data that was NOT used to pick the threshold."""
    from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
    labels = labels.copy()
    rule = detector.meta.get("resample_rule")
    if rule:
        labels = labels.resample(rule).max()
    y = labels.reindex(result.index).fillna(0).astype(int).to_numpy()
    if not 0 < y.sum() < len(y):
        return {"note": "labels have no positives or no negatives in the scored range"}
    flags = result["alert"].to_numpy()
    p, r, f, _ = precision_recall_fscore_support(y, flags, average="binary", zero_division=0)
    return {"timesteps": len(y), "attacked": int(y.sum()), "roc_auc": roc_auc_score(y, result["score"]),
            "pr_auc": average_precision_score(y, result["score"]), "precision": p, "recall": r, "f1": f,
            "flagged": float(flags.mean())}


def _model_type_from_weights(state):
    keys = list(state)
    if any(k.startswith("enc_gru.") for k in keys):
        return "gru"
    if any(k.startswith("encoder.0.") for k in keys):
        return "dense"
    return None


class AutoencoderDetector:
    """model_class: optional. Pass your own nn.Module class if you trained a custom autoencoder. It is built as
    model_class(n_feat, window, hidden, bottleneck, dropout) and must take and return FLATTENED windows
    (batch, window * n_feat)."""

    def __init__(self, output_dir="outputs", device=None, model_class=None):
        out = Path(output_dir)
        self.meta = json.loads((out / "meta.json").read_text())
        a = self.meta["autoencoder"]
        self.features = list(self.meta["feature_cols"])
        self.scaler = joblib.load(out / "scaler.joblib")
        self.window, self.topk = int(a["window"]), int(a["topk"])
        self.max_gap_fill = int(self.meta.get("max_gap_fill", 5))
        self.threshold = float(a["feature_threshold"])
        self.scale = np.asarray(a["feature_scale"], dtype=np.float64)
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        state = torch.load(out / a["weights"], map_location=self.device)
        if model_class is None:
            kind = _model_type_from_weights(state)           # decided from the saved layer names, not from meta.json
            if kind is None:
                raise ValueError("These weights were not made by this notebook's dense or GRU autoencoder "
                                 f"(layer names start with {sorted({k.split('.')[0] for k in state})}). "
                                 "Pass your own class: AutoencoderDetector(dir, model_class=YourClass)")
            model_class = GRUAutoencoder if kind == "gru" else WindowAutoencoder
        self.model = model_class(len(self.features), self.window, a["hidden"], a["bottleneck"], a["dropout"]).to(self.device)
        try:
            self.model.load_state_dict(state)
        except RuntimeError as e:
            raise RuntimeError("Saved weights do not match the model class (different layers or sizes). "
                               "Check window/hidden/bottleneck in meta.json and that model_class is the class you trained with.\n"
                               + str(e)[:400]) from None
        self.model.eval()

    def prepare(self, wide):
        """Resample one file, fill gaps as in training, standardize and clip."""
        if not isinstance(wide.index, pd.DatetimeIndex):
            raise ValueError("wide must be indexed by timestamp")
        X = wide.sort_index()
        rule = self.meta.get("resample_rule")
        if rule:
            X = X.resample(rule).mean()
        missing = [c for c in self.features if c not in X.columns]
        if missing:
            raise ValueError(f"Input file is missing {len(missing)} training features: {missing[:10]}")
        X = X.reindex(columns=self.features)
        X = X.interpolate(limit=self.max_gap_fill).ffill()
        saved_fill = self.meta.get("fill_values")
        if saved_fill is not None:
            fill = pd.Series(saved_fill, dtype="float64") if isinstance(saved_fill, dict) else pd.Series(saved_fill, index=self.features)
            fill = fill.reindex(self.features)
            if fill.isna().any():
                raise ValueError("meta.json fill_values is missing one or more training features")
        else:
            fill = pd.Series(self.scaler.mean_, index=self.features)
            if X.isna().any().any():
                warnings.warn("meta.json has no training medians: using scaler means for remaining missing "
                              "values. Save training fill_values in meta.json for exact notebook preprocessing.")
        X = X.fillna(fill).astype("float32")
        S = np.clip(self.scaler.transform(X), -10, 10).astype(np.float32)
        return X.index, S

    @torch.no_grad()
    def score(self, wide, batch_size=512):
        """One row per scored timestep (the first window-1 timesteps have no full window and are not scored)."""
        index, S = self.prepare(wide)
        n, n_feat = S.shape
        if n < self.window:
            raise ValueError(f"need at least {self.window} timesteps, got {n}")
        arr = torch.from_numpy(S).to(self.device)
        ar = torch.arange(self.window, device=self.device)
        n_win = n - self.window + 1
        errs = []
        for s in range(0, n_win, batch_size):
            idx = torch.arange(s, min(s + batch_size, n_win), device=self.device)
            xb = arr[idx[:, None] + ar].reshape(len(idx), -1)
            errs.append(((self.model(xb) - xb)[:, -n_feat:] ** 2).cpu())     # error of each window's LAST step
        z = torch.cat(errs).numpy() / self.scale                              # per-feature standardized error
        k = min(max(self.topk, 1), n_feat)
        top_idx = np.argsort(z, axis=1)[:, -k:][:, ::-1]                      # k largest, biggest first
        top_val = np.take_along_axis(z, top_idx, axis=1)
        res = pd.DataFrame({"score": top_val.mean(axis=1)}, index=index[self.window - 1:])
        res["alert"] = res["score"] > self.threshold
        res["top_features"] = [[self.features[j] for j in row] for row in top_idx]
        res["top_feature_scores"] = [row.round(2).tolist() for row in top_val]
        return res

    def score_latest(self, recent):
        """For streaming: pass the most recent rows (at least `window`, ideally a few more) and get the newest row's result."""
        return self.score(recent).iloc[-1]


def score_files(detector, paths, *, timestamp_col="simulated_at", value_col="value",
                id_cols=("asset_id", "metric"), facility_col="facility_id",
                label_col="is_attack", wide_format=False):
    """Score each CSV independently, matching the training notebook's file boundaries."""
    results, label_parts = [], []
    for path in paths:
        if wide_format:
            frame = pd.read_csv(path)
            frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], errors="coerce")
            frame = (frame.dropna(subset=[timestamp_col]).sort_values(timestamp_col)
                     .drop_duplicates(timestamp_col).set_index(timestamp_col))
            labels = frame[label_col] if label_col and label_col in frame else None
            wide = frame.select_dtypes("number").drop(columns=[label_col], errors="ignore").astype("float32")
        else:
            wide, labels = load_wide([path], timestamp_col, value_col, id_cols,
                                     facility_col, label_col)
        if len(wide) == 0:
            raise ValueError(f"No usable rows in {path}")
        results.append(detector.score(wide))
        if labels is not None:
            label_parts.append(labels)
    if not results:
        raise ValueError("No input files to score")
    result = pd.concat(results).sort_index()
    if result.index.has_duplicates:
        raise ValueError("Input files contain overlapping scored timestamps; "
                         "score_files requires non-overlapping files")
    labels = pd.concat(label_parts).groupby(level=0).max().sort_index() if label_parts else None
    return result, labels


def export_anomaly_rows(paths, result, output_path, *, timestamp_col="simulated_at",
                        value_col="value", id_cols=("asset_id", "metric"),
                        facility_col="facility_id", resample_rule=None,
                        wide_format=False, chunksize=100_000):
    """Locate input records associated with alerts; source_row is zero-based after the CSV header.

    In long format, keep only rows for the top-k features of each alerted timestep.
    A resampled score refers to the entire time bin; duplicate input records for
    the same feature and bin are all included. This is attribution of a timestep
    alert, not a separate prediction of whether each raw record is anomalous.
    """
    alerts = result.loc[result["alert"]]
    keys = ([facility_col] if facility_col else []) + list(id_cols)
    if wide_format:
        output_cols = ["source_file", "source_row", timestamp_col, "score_timestamp",
                       "score", "top_features", "top_feature_scores"]
    else:
        output_cols = ["source_file", "source_row", timestamp_col, *keys, value_col,
                       "feature", "score_timestamp", "score", "feature_score", "feature_rank"]
    if alerts.empty:
        pd.DataFrame(columns=output_cols).to_csv(output_path, index=False)
        return 0

    if wide_format:
        lookup = alerts.reset_index().rename(columns={alerts.index.name or "index": "_score_time"})
        lookup = lookup[["_score_time", "score", "top_features", "top_feature_scores"]]
    else:
        lookup = pd.DataFrame(
            [(t, feature, row.score, error, rank)
             for t, row in alerts.iterrows()
             for rank, (feature, error) in enumerate(zip(row.top_features, row.top_feature_scores), 1)],
            columns=["_score_time", "_feature", "score", "feature_score", "feature_rank"])

    total = 0
    wrote_header = False
    for path in paths:
        columns = None if wide_format else [timestamp_col, *keys, value_col]
        row_offset = 0
        for chunk in pd.read_csv(path, usecols=columns, chunksize=chunksize):
            chunk["source_file"] = str(path)
            chunk["source_row"] = np.arange(row_offset, row_offset + len(chunk))
            row_offset += len(chunk)
            chunk["_timestamp"] = pd.to_datetime(chunk[timestamp_col], errors="coerce")
            chunk = chunk.loc[chunk["_timestamp"].notna()].copy()
            if not wide_format:
                chunk = chunk.loc[chunk[value_col].notna()].copy()
            if chunk.empty:
                continue

            # Match pandas' resampling bins (including anchored calendar rules).
            # This uses the same rule and default origin as prepare().
            if resample_rule:
                score_time = pd.Series(pd.NaT, index=chunk.index, dtype=result.index.dtype)
                for bin_time, group in chunk.groupby(
                        pd.Grouper(key="_timestamp", freq=resample_rule)):
                    score_time.loc[group.index] = bin_time
                chunk["_score_time"] = score_time
            else:
                chunk["_score_time"] = chunk["_timestamp"]

            if not wide_format:
                feature = chunk[keys[0]].astype(str)
                for key in keys[1:]:
                    feature = feature + "__" + chunk[key].astype(str)
                chunk["_feature"] = feature

            matched = chunk.merge(lookup, how="inner", on=["_score_time"] if wide_format
                                  else ["_score_time", "_feature"], sort=False)
            if matched.empty:
                continue
            matched = matched.rename(columns={"_score_time": "score_timestamp",
                                              "_feature": "feature"})
            if wide_format:
                matched["top_features"] = matched["top_features"].map("|".join)
                matched["top_feature_scores"] = matched["top_feature_scores"].map(
                    lambda values: "|".join(map(str, values)))
            matched[output_cols].to_csv(output_path, mode="a" if wrote_header else "w",
                                        header=not wrote_header, index=False)
            wrote_header = True
            total += len(matched)

    if not wrote_header:
        pd.DataFrame(columns=output_cols).to_csv(output_path, index=False)
    return total


if __name__ == "__main__":
    # python ae_inference.py "daily_chunks/guardfleet_february_attacked_*.csv.gz" --outputs outputs --save scores.csv
    import argparse

    ap = argparse.ArgumentParser(description="Score CSV file(s) with the trained autoencoder (per-feature top-k score).")
    ap.add_argument("csv", nargs="+", help="file(s) or glob pattern(s); pass chunks in any order, they are joined by time")
    ap.add_argument("--outputs", default="outputs", help="folder with meta.json, scaler.joblib, autoencoder_best.pt")
    ap.add_argument("--save", default="scores.csv", help="where to write the results")
    ap.add_argument("--anomaly-rows", default="anomaly_rows.csv",
                    help="where to write original input rows associated with alerts")
    ap.add_argument("--wide", action="store_true", help="files already have one column per feature (default: long log format)")
    ap.add_argument("--timestamp-col", default="simulated_at")
    ap.add_argument("--value-col", default="value")
    ap.add_argument("--facility-col", default="facility_id", help="use '' if there is none")
    ap.add_argument("--label-col", default="is_attack", help="0/1 attack column; if present, metrics are printed")
    args = ap.parse_args()

    paths = sorted({p for pat in args.csv for p in (glob.glob(pat) or [pat])})
    print(f"{len(paths)} file(s)")
    detector = AutoencoderDetector(args.outputs)          # <- the constructor runs here: loads scaler, meta, weights
    result, labels = score_files(
        detector, paths, timestamp_col=args.timestamp_col, value_col=args.value_col,
        facility_col=args.facility_col or None, label_col=args.label_col,
        wide_format=args.wide)
    if labels is not None:
        result["is_attack"] = labels.resample(detector.meta["resample_rule"]).max().reindex(result.index).fillna(0).astype(int) \
            if detector.meta.get("resample_rule") else labels.reindex(result.index).fillna(0).astype(int)
    out = result.copy()
    out["top_features"] = out["top_features"].map("|".join)
    out["top_feature_scores"] = out["top_feature_scores"].map(lambda v: "|".join(map(str, v)))
    out.to_csv(args.save)
    matched_rows = export_anomaly_rows(
        paths, result, args.anomaly_rows, timestamp_col=args.timestamp_col,
        value_col=args.value_col, facility_col=args.facility_col or None,
        resample_rule=detector.meta.get("resample_rule"), wide_format=args.wide)
    print(f"scored {len(result):,} timesteps; {int(result.alert.sum()):,} alerts "
          f"({result.alert.mean():.2%}); threshold {detector.threshold:.4g}; saved to {args.save}")
    print(f"matched {matched_rows:,} original input rows; saved to {args.anomaly_rows}")
    if labels is not None:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in evaluate(detector, result, labels).items()})
    print(result[result.alert].head(5).drop(columns=["is_attack"], errors="ignore").to_string())
