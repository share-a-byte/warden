export type Asset = { id: string; room: number; x: number; z: number; product: string; baseline: number; firmware: string };
export const rooms = ["Vaccine storage", "Biologics storage", "Dispatch & quarantine"];
export const assets: Asset[] = Array.from({ length: 20 }, (_, i) => {
  const room = i < 8 ? 0 : i < 16 ? 1 : 2;
  const local = i - (room === 0 ? 0 : room === 1 ? 8 : 16);
  return { id: `FR-${String(i + 1).padStart(2, "0")}`, room, x: -9 + room * 9 + (local % 2) * 3.4, z: -4.4 + Math.floor(local / 2) * 2.8, product: ["Vaccine inventory", "Temperature-sensitive biologics", "Outbound medicine batches"][room], baseline: 4.1 + (i % 4) * .2, firmware: "v1.2.0" };
});
export const replaySteps = [
  { title: "Normal operation", detail: "All 20 units report nominal telemetry. Independent safety controllers are monitoring.", time: "00:00" },
  { title: "Network controller compromised", detail: "FR-08 receives an unauthorized compressor command through its network-facing Pico.", time: "00:05" },
  { title: "Sensor anomaly detected", detail: "FR-08 reaches 8.9°C, above the illustrative 2–8°C operating band. The local temperature sensor disagrees with the command.", time: "00:10" },
  { title: "Independent safety veto", detail: "The Arduino rejects the command and opens the control relay. Isolation is active; temperature recovery is not yet confirmed.", time: "00:15" },
  { title: "Fleet investigation", detail: "A related suspicious command appears on FR-14. FR-08 remains isolated while the fleet is inspected.", time: "00:20" },
];
export function telemetry(asset: Asset, step: number) {
  const attacked = asset.id === "FR-08" && step >= 1;
  const related = asset.id === "FR-14" && step >= 4;
  const veto = attacked && step >= 3;
  const temperature = attacked && step >= 2 ? 8.9 : asset.baseline;
  return { attacked, related, veto, temperature, status: veto ? "Safety veto active" : attacked || related ? "Threat detected" : "Nominal", color: veto ? "#ffc879" : attacked || related ? "#ff6785" : "#6be4cf", anomaly: attacked ? (step >= 2 ? .97 : .73) : related ? .81 : .03, relay: veto ? "Opened by Arduino" : "Closed", readings: [asset.baseline-.2,asset.baseline,asset.baseline+.1,asset.baseline-.1,asset.baseline,attacked && step>=2 ? 5.2 : asset.baseline+.2,attacked && step>=2 ? 7.1 : asset.baseline+.1,temperature] };
}
