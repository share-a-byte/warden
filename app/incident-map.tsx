"use client";

import { useState } from "react";

type Site = { id: string; name: string; area: string; lat: number; lng: number };
// Illustrative severity scores (1–5); replace with incident data from the backend.
const demoSeverity: Record<string, number> = { "SF-01": 1, "SF-02": 3, "SF-03": 5, "SF-04": 2, "SF-05": 4, "SF-06": 1, "SF-07": 2, "SF-08": 5 };
function mercator(lat: number, lng: number) {
  const size = 256 * 2 ** 12;
  return { x: (lng + 180) / 360 * size, y: (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * size };
}
const origin = mercator(37.773, -122.433);
export default function IncidentMap({ sites, selected, onSelect }: { sites: Site[]; selected: string; onSelect: (site: Site) => void }) {
  const [rotation, setRotation] = useState(0);
  const [scale, setScale] = useState(1);
  const [failed, setFailed] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const angle = rotation * Math.PI / 180;
  const a = Math.cos(angle) * scale, c = -Math.sin(angle) * scale;
  const b = Math.sin(angle) * scale, d = Math.cos(angle) * scale;
  function project(x: number, y: number) { return [500 + a*x + c*y, 330 + b*x + d*y]; }
  const tiles = [];
  for (let dx=-2;dx<=2;dx++) for (let dy=-2;dy<=2;dy++) {
    const x = Math.floor(origin.x/256)+dx, y = Math.floor(origin.y/256)+dy;
    tiles.push(<image key={`${x}-${y}`} href={`https://tile.openstreetmap.org/12/${x}/${y}.png`} x={x*256-origin.x} y={y*256-origin.y} width="256" height="256" onError={() => setFailed(true)} />);
  }
  const points = sites.map(site => {
    const position = mercator(site.lat, site.lng);
    return { site, severity: demoSeverity[site.id], x: position.x-origin.x, y: position.y-origin.y };
  }).sort((a,b) => a.severity-b.severity);
  const active = sites.find(s => s.id === (hovered ?? selected));
  return <div className="risk-map">
    <div className="risk-map-heading"><span><i /> INCIDENT SEVERITY</span><small>Illustrative severity · 1–5 scale</small></div>
    <svg viewBox="0 0 1000 620" className="risk-scene" aria-label="San Francisco incident map. Larger neon points represent higher demo severity.">
      <defs><filter id="dark-map"><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncR type="linear" slope="-.22" intercept=".26"/><feFuncG type="linear" slope="-.22" intercept=".25"/><feFuncB type="linear" slope="-.22" intercept=".3"/></feComponentTransfer></filter><radialGradient id="map-glow"><stop stopColor="#00bfff" stopOpacity=".17"/><stop offset="1" stopColor="#0c0c10" stopOpacity="0"/></radialGradient></defs>
      <rect width="1000" height="620" fill="url(#map-glow)"/>
      <g transform={`matrix(${a} ${b} ${c} ${d} 500 330)`} filter="url(#dark-map)">{tiles}</g>
      {points.map(point => {
        const [x,y] = project(point.x,point.y);
        const radius = 3 + point.severity * 1.8;
        const color = point.severity >= 4 ? "#90ffdc" : "#00caff";
        const emphasized = point.site.id === (hovered ?? selected);
        return <g key={point.site.id} role="button" tabIndex={0} aria-label={`${point.site.area}: demo severity ${point.severity} of 5`} onClick={()=>onSelect(point.site)} onFocus={()=>setHovered(point.site.id)} onBlur={()=>setHovered(null)} onMouseEnter={()=>setHovered(point.site.id)} onMouseLeave={()=>setHovered(null)} onKeyDown={e=>{if(e.key==="Enter" || e.key===" "){e.preventDefault();onSelect(point.site);}}} className="risk-point">
          <title>{point.site.area}: demo severity {point.severity}/5</title>
          <circle cx={x} cy={y} r={Math.max(22,radius*2.5)} fill="transparent" />
          <circle cx={x} cy={y} r={radius*2.5} fill={color} opacity=".045" pointerEvents="none" />
          <circle cx={x} cy={y} r={radius*1.8} fill={color} opacity=".09" pointerEvents="none" />
          <circle cx={x} cy={y} r={radius*1.3} fill={color} opacity=".16" pointerEvents="none" />
          <circle className="point-core" cx={x} cy={y} r={radius} fill={color} opacity=".9" pointerEvents="none" />
          <circle cx={x} cy={y} r={radius*.35} fill="#e1ffff" pointerEvents="none" />
          {emphasized && <g pointerEvents="none"><circle cx={x} cy={y} r={radius+7} fill="none" stroke="#ccfbff" strokeWidth="1" strokeDasharray="3 4"/><text x={x} y={y-radius-17} textAnchor="middle" fill="#ddfbff" fontSize="12" fontWeight="600" stroke="#0a1016" strokeWidth="4" paintOrder="stroke">{point.site.area} · {point.severity}/5</text></g>}
        </g>;
      })}
    </svg>
    {failed && <div className="risk-error">Basemap unavailable. Demo points remain visible.</div>}
    {!sites.length && <div className="risk-empty">No sites match your filters.</div>}
    <div className="risk-controls"><button aria-label="Rotate map left" onClick={()=>setRotation(r=>Math.max(-40,r-10))} disabled={rotation<=-40}>↶</button><button aria-label="Rotate map right" onClick={()=>setRotation(r=>Math.min(40,r+10))} disabled={rotation>=40}>↷</button><button aria-label="Zoom incident map in" onClick={()=>setScale(s=>Math.min(1.5,s+.1))} disabled={scale>=1.5}>+</button><button aria-label="Zoom incident map out" onClick={()=>setScale(s=>Math.max(.7,s-.1))} disabled={scale<=.7}>−</button><button aria-label="Reset incident map" onClick={()=>{setRotation(0);setScale(1);}}>⌖</button></div>
    <div className="risk-bottom"><div className="risk-key"><b>Incident severity</b><span><i/><i/><i/><i/> Low <span>→</span> High</span><small>Larger point = higher severity · Illustrative data</small></div>{active && <div className="risk-readout"><strong>{demoSeverity[active.id]}<small>/5</small></strong><span>demo severity<small>{active.area}</small></span></div>}</div>
    <a className="attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
  </div>;
}
