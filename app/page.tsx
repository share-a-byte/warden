"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import IncidentMap from "./incident-map";

type Status = "Critical" | "Attention" | "Operational";
const sites: { id: string; name: string; area: string; lat: number; lng: number; status: Status; note: string; team: string }[] = [
  { id: "SF-01", name: "Marina Station", area: "Marina District", lat: 37.803, lng: -122.438, status: "Operational", note: "All systems running normally", team: "Team Alpha" },
  { id: "SF-02", name: "Presidio Gateway", area: "Presidio", lat: 37.791, lng: -122.469, status: "Attention", note: "Backup power inspection required", team: "Team Bravo" },
  { id: "SF-03", name: "Downtown Hub", area: "Financial District", lat: 37.794, lng: -122.402, status: "Critical", note: "Primary network connection offline", team: "Team Alpha" },
  { id: "SF-04", name: "Richmond Outpost", area: "Inner Richmond", lat: 37.779, lng: -122.465, status: "Operational", note: "All systems running normally", team: "Team Charlie" },
  { id: "SF-05", name: "Mission Control", area: "Mission District", lat: 37.758, lng: -122.418, status: "Attention", note: "Elevated equipment temperature", team: "Team Bravo" },
  { id: "SF-06", name: "Sunset Depot", area: "Inner Sunset", lat: 37.756, lng: -122.473, status: "Operational", note: "All systems running normally", team: "Team Charlie" },
  { id: "SF-07", name: "SoMa Operations", area: "South of Market", lat: 37.777, lng: -122.404, status: "Operational", note: "All systems running normally", team: "Team Alpha" },
  { id: "SF-08", name: "Bayview Facility", area: "Bayview", lat: 37.736, lng: -122.389, status: "Critical", note: "Access sensor requires response", team: "Team Delta" },
];
const colors: Record<Status, string> = { Critical: "#f08080", Attention: "#f6d871", Operational: "#80e3ad" };
function point(lat: number, lng: number, zoom: number) {
  const scale = 256 * 2 ** zoom;
  return { x: (lng + 180) / 360 * scale, y: (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * scale };
}
// Keep CSS serialization stable across SSR and browser style normalization.
function mapOffset(value: number) {
  const rounded = Math.round(value * 100) / 100;
  return `calc(50% ${rounded < 0 ? "-" : "+"} ${Math.abs(rounded)}px)`;
}

export default function Home() {
  const [mapMode, setMapMode] = useState<"incidents" | "sites">("incidents");
  const [filter, setFilter] = useState<Status | "All sites">("All sites");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(sites[2]);
  const [zoom, setZoom] = useState(12);
  const [center, setCenter] = useState({ lat: 37.773, lng: -122.433 });
  const [failed, setFailed] = useState(false);
  const visible = sites.filter(s => (filter === "All sites" || s.status === filter) && `${s.name} ${s.area} ${s.id}`.toLowerCase().includes(query.toLowerCase()));
  const origin = point(center.lat, center.lng, zoom);
  const tiles = [];
  for (let dx = -3; dx <= 3; dx++) for (let dy = -2; dy <= 2; dy++) {
    const x = Math.floor(origin.x / 256) + dx, y = Math.floor(origin.y / 256) + dy;
    // Map tiles must retain their exact native dimensions and public cache URLs.
    // eslint-disable-next-line @next/next/no-img-element
    tiles.push(<img key={`${zoom}-${x}-${y}`} alt="" draggable={false} src={`https://tile.openstreetmap.org/${zoom}/${x}/${y}.png`} onError={() => setFailed(true)} style={{ left: mapOffset(x * 256 - origin.x), top: mapOffset(y * 256 - origin.y) }} />);
  }
  function focus(site: typeof sites[number]) { setSelected(site); setCenter({ lat: site.lat, lng: site.lng }); }
  return <div className="shell">
    <aside className="sidebar"><Link className="brand" href="/"><Image className="brand-logo" src="/warden-logo.png" alt="" width={52} height={52} priority /><span>warden<span className="brand-dot">.</span></span></Link><div className="workspace"><span className="workspace-icon">W</span><div>West Coast Operations<small>Operations workspace</small></div><span>⌄</span></div><p className="nav-label">WORKSPACE</p><nav className="overview-tabs" aria-label="Main navigation"><Link className="nav-active" href="/" aria-current="page">Fleet overview</Link><Link href="/facility">Facility explorer</Link></nav><div className="side-note">Your operations.<br />One clear picture.</div><div className="sidebar-bottom"><span className="avatar">JD</span><div>Jamie Davis<small>Operations manager</small></div></div></aside>
    <main><header><div>Workspace <span>/</span> <b>Overview</b></div><span className="demo">● Demo workspace</span></header><div className="content"><div className="heading"><div><p className="eyebrow">OPERATIONS OVERVIEW</p><h1>Eyes on every operation.</h1><p>Monitor your sites, spot issues, and keep things moving.</p></div><div className="region">◎ &nbsp; San Francisco, CA</div></div>
      <div className="stats">{(["All sites", "Operational", "Attention", "Critical"] as const).map((status, i) => <button key={status} className={`stat ${filter === status ? "stat-active" : ""}`} onClick={() => setFilter(status)}><span>{i === 0 ? "Total sites" : status}<span style={{ color: i ? colors[status as Status] : "#7c8580" }}>●</span></span><strong>{i === 0 ? sites.length : sites.filter(s => s.status === status).length}<small>{["Across your network", "Running as expected", "Needs a closer look", "Immediate action needed"][i]}</small></strong></button>)}</div>
      <section className="operations"><div className="section-heading"><div><h2>Operations map</h2><span>A real-world view of your network</span></div><div className="map-mode"><button className={mapMode === "incidents" ? "active" : ""} aria-pressed={mapMode === "incidents"} onClick={() => setMapMode("incidents")}>Neon incidents</button><button className={mapMode === "sites" ? "active" : ""} aria-pressed={mapMode === "sites"} onClick={() => setMapMode("sites")}>Site pins</button></div></div><div className="toolbar"><div className="filters">{(["All sites", "Critical", "Attention", "Operational"] as const).map(s => <button aria-pressed={filter === s} key={s} onClick={() => setFilter(s)} className={filter === s ? "active" : ""}>{s !== "All sites" && <i style={{ backgroundColor: colors[s] }} />}{s}</button>)}</div><input aria-label="Search sites" placeholder="Search sites…" value={query} onChange={e => setQuery(e.target.value)} /></div>
        <div className="map-layout">{mapMode === "incidents" ? <IncidentMap sites={visible} selected={selected.id} onSelect={site => { const match = sites.find(s => s.id === site.id); if (match) setSelected(match); }} /> : <div className="map" aria-label="San Francisco operations map"><div className="tiles">{tiles}</div>{failed && <div className="map-error">Map imagery unavailable. Check your connection.</div>}<div className="map-badge"><i /> San Francisco network</div>{visible.map(s => { const p = point(s.lat, s.lng, zoom); return <button title={`${s.name}: ${s.status}`} aria-label={`${s.name}: ${s.status}`} key={s.id} className={`pin ${selected.id === s.id ? "selected" : ""}`} style={{ left: mapOffset(p.x - origin.x), top: mapOffset(p.y - origin.y), backgroundColor: colors[s.status] }} onClick={() => setSelected(s)}><span /></button>; })}<div className="map-controls"><button aria-label="Zoom in" disabled={zoom === 15} onClick={() => setZoom(z => z + 1)}>+</button><button aria-label="Zoom out" disabled={zoom === 11} onClick={() => setZoom(z => z - 1)}>−</button><button aria-label="Reset map" onClick={() => { setCenter({ lat: 37.773, lng: -122.433 }); setZoom(12); }}>⌖</button></div><div className="map-legend">{Object.entries(colors).map(([s, color]) => <span key={s}><i style={{ backgroundColor: color }} />{s}</span>)}</div><a className="attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a></div>}
        <aside className="site-panel"><div className="panel-heading"><h3>Sites</h3><span>{visible.length} locations</span></div><div className="site-list">{visible.length ? visible.map(s => <button className={`site ${selected.id === s.id ? "site-selected" : ""}`} key={s.id} onClick={() => focus(s)}><span className="site-icon" style={{ color: colors[s.status] }}>◈</span><span><b>{s.name}</b><small>{s.area}</small></span><i style={{ backgroundColor: colors[s.status] }} /></button>) : <p className="empty">No sites match your filters.</p>}</div><div className="site-detail"><span className="detail-label">SELECTED SITE · {selected.id}</span><h3>{selected.name}</h3><span className="status" style={{ color: colors[selected.status] }}>● {selected.status}</span><p>{selected.note}</p><div>Assigned team <b>{selected.team}</b></div></div></aside></div>
      </section><section className="incidents"><div className="section-heading"><div><h2>Needs your attention <span className="count">4</span></h2><span>Open issues across your network</span></div></div><div className="incident-grid">{sites.filter(s => s.status !== "Operational").map(s => <button key={s.id} onClick={() => { setFilter("All sites"); setQuery(""); focus(s); }}><span className="incident-dot" style={{ backgroundColor: colors[s.status] }} /><div><b>{s.note}</b><small>{s.name} <span>·</span> {s.team}</small></div><span>↗</span></button>)}</div></section><footer><span><i /> Network overview</span><span>Demo data · 8 monitored locations</span></footer>
    </div></main>
  </div>;
}
