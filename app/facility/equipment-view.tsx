"use client";
import { telemetry, type Asset } from "./data";
const components = [
  { name: "Temperature sensor", tag: "01", subtitle: "Local chamber measurement", x: 279, y: 208, color: "#64e4ef" },
  { name: "Network Pico", tag: "02", subtitle: "Remote command interface", x: 322, y: 425, color: "#c0a1f5" },
  { name: "Safety Arduino", tag: "03", subtitle: "Independent safety decision", x: 221, y: 425, color: "#6be4cf" },
  { name: "Control relay", tag: "04", subtitle: "Physical command isolation", x: 123, y: 425, color: "#ffc879" },
];
export default function EquipmentView({asset,step,component,onComponent,onBack}:{asset:Asset;step:number;component:string;onComponent:(name:string)=>void;onBack:()=>void}) {
 const state=telemetry(asset,step);
 return <div className="equipment-workbench"><div className="workbench-heading"><div><span>EQUIPMENT / {asset.id}</span><h3>Inside the refrigeration unit</h3><p>Illustrative cutaway · not a manufacturer CAD model</p></div><button onClick={onBack}>↖ Facility</button></div>
 <div className="workbench-body"><svg className="cabinet-diagram" viewBox="0 0 440 540" role="img" aria-label={`${asset.id} cutaway showing refrigerated shelves, air circulation, temperature probe, and control electronics`}>
 <defs><linearGradient id="cabinet-metal" x2="1" y2="1"><stop stopColor="#5a6b7c"/><stop offset=".5" stopColor="#243444"/><stop offset="1" stopColor="#71818b"/></linearGradient><linearGradient id="chamber" x2="0" y2="1"><stop stopColor="#173d4c"/><stop offset="1" stopColor="#0d1e2c"/></linearGradient></defs>
 <ellipse cx="215" cy="508" rx="165" ry="18" fill="#000" opacity=".35"/>
 <path d="M72 64 L335 64 L368 85 L368 480 L335 499 L72 499Z" fill="#182735" stroke="#536979"/>
 <path d="M72 64H335V499H72Z" fill="url(#cabinet-metal)" stroke="#8e9ba8"/>
 <rect x="85" y="77" width="238" height="43" rx="3" fill="#18202a"/>
 <rect x="104" y="87" width="68" height="23" rx="3" fill="#081e25" stroke="#386d78"/><text x="138" y="103" fill={state.temperature>8?"#ff7891":"#80f0dd"} fontSize="14" textAnchor="middle">{state.temperature.toFixed(1)}°C</text><text x="302" y="101" fill="#bccdd9" fontSize="9" textAnchor="end">{asset.id} / COLD STORAGE</text>
 <rect x="88" y="132" width="230" height="244" rx="6" fill="url(#chamber)" stroke="#91aab6" strokeWidth="3"/>
 {[185,250,315,365].map(y=><g key={y}><rect x="99" y={y} width="208" height="5" fill="#78909d"/>{Array.from({length:16},(_,i)=><path key={i} d={`M${102+i*13} ${y}v8`} stroke="#496678"/>)}</g>)}
 {[215,280,345].map(y=><g key={y}>{[118,157,196,235].map(x=><g key={x}><rect x={x} y={y-19} width="24" height="29" rx="2" fill="#b3c4c9"/><rect x={x+2} y={y-15} width="20" height="4" fill="#6ca5b3"/><rect x={x+5} y={y-7} width="14" height="8" fill="#dce9e6"/></g>)}</g>)}
 <circle cx="202" cy="155" r="14" fill="#142832" stroke="#7795a2"/>{[0,90,180,270].map(angle=><path key={angle} d="M202 155q-10-15 0-12q8 4 0 12" fill="#6a8996" transform={`rotate(${angle} 202 155)`}/>)}
 <path d="M293 170v178" stroke="#54c9e2" strokeDasharray="5 6" opacity=".6"/><path d="M289 340l4 8 4-8" fill="none" stroke="#54c9e2"/>
 <rect x="91" y="391" width="224" height="85" rx="4" fill="#0c141c" stroke="#556978"/>
 <path d="M279 208v180h-58v37M221 425h-98M322 425h-67" fill="none" stroke="#53778d" strokeWidth="2"/>
 {components.map(part=><g key={part.name} role="button" tabIndex={0} aria-label={`Inspect ${part.name}`} onClick={()=>onComponent(part.name)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();onComponent(part.name);}}} className="cabinet-part">
 {part.tag==="01"?<><path d="M279 195v25" stroke="#b9e8f3" strokeWidth="5"/><circle cx="279" cy="219" r="5" fill={part.color}/></>:<><rect x={part.x-21} y={part.y-14} width="42" height="28" rx="3" fill={part.tag==="04"?"#5a4d33":"#244f4a"} stroke={part.color}/><rect x={part.x-7} y={part.y-7} width="14" height="14" fill="#101a22"/>{[-15,-10,-5,0,5,10,15].map(dx=><path key={dx} d={`M${part.x+dx} ${part.y-18}v4M${part.x+dx} ${part.y+14}v4`} stroke="#c5c9b4"/>)}</>}
 <circle cx={part.x} cy={part.y} r="30" fill="transparent" stroke={component===part.name?part.color:"transparent"} strokeWidth="2"/><circle cx={part.x+22} cy={part.y-21} r="11" fill={part.color}/><text x={part.x+22} y={part.y-17} textAnchor="middle" fontSize="10" fill="#111827">{part.tag}</text>
 </g>)}
 <rect x="88" y="499" width="25" height="9" rx="2" fill="#586875"/><rect x="292" y="499" width="25" height="9" rx="2" fill="#586875"/>
 </svg><div className="workbench-components"><span className="workbench-label">SELECT A COMPONENT</span>{components.map(part=><button key={part.name} onClick={()=>onComponent(part.name)} aria-pressed={component===part.name}><span className="component-number" style={{color:part.color}}>{part.tag}</span><span><b>{part.name}</b><small>{part.subtitle}</small></span><span>↗</span></button>)}<div className="safety-path"><span>COMMAND PATH</span><p>Pico → <b>Relay</b> → Actuator</p><span>INDEPENDENT SAFETY PATH</span><p>Sensor → <b>Arduino</b> → Relay veto</p><div style={{color:state.veto?"#ffc879":"#6be4cf"}}>{state.veto?"◇ Remote command isolated":"● Safety controller monitoring"}</div></div></div></div></div>;
}
