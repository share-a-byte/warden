"use client";
import { Component, useEffect, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Image from "next/image";
import { assets, rooms, replaySteps, telemetry } from "./data";
import "./facility.css";
import EquipmentView from "./equipment-view";
const Scene = dynamic(()=>import("./scene"),{ssr:false,loading:()=> <div className="scene-fallback">Loading facility geometry…</div>});
class SceneBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed ? <div className="scene-fallback">3D rendering is unavailable on this device. You can still inspect equipment and run the replay using the controls below.</div> : this.props.children;}
}
export default function FacilityPage(){
  const [selected,setSelected]=useState("FR-08");
  const [mode,setMode]=useState<"solid"|"lidar">("lidar");
  const [detail,setDetail]=useState(false);
  const [room,setRoom]=useState(-1);
  const [reset,setReset]=useState(0);
  const [component,setComponent]=useState("Temperature sensor");
  const [step,setStep]=useState(0);
  const [playing,setPlaying]=useState(false);
  const asset=assets.find(a=>a.id===selected)!;
  const state=telemetry(asset,step);
  useEffect(()=>{
    if(!playing)return;
    const timer=setTimeout(()=>{
      if(step>=4){setPlaying(false);return;}
      setStep(step+1);
      if(step===0){setSelected("FR-08");setDetail(true);setRoom(-1);setComponent("Network Pico");}
      if(step===1)setComponent("Temperature sensor");
      if(step===2)setComponent("Safety Arduino");
      if(step===3){setDetail(false);setRoom(-1);setPlaying(false);}
    },4500);
    return ()=>clearTimeout(timer);
  },[playing,step]);
  function select(id:string){setSelected(id);}
  function stage(index:number){setPlaying(false);setStep(index);setSelected("FR-08");setRoom(-1);setDetail(index>0&&index<4);setComponent(index===1?"Network Pico":index===3?"Safety Arduino":"Temperature sensor");}
  const threats=assets.filter(a=>{const s=telemetry(a,step);return s.attacked||s.related;}).length;
  const vetoes=assets.filter(a=>telemetry(a,step).veto).length;
  return <div className="shell facility-shell">
    <nav className="facility-nav" aria-label="Main navigation"><Link className="brand" href="/"><Image className="brand-logo" src="/warden-logo.png" alt="" width={52} height={52}/><span>warden<span className="brand-dot">.</span></span></Link><div className="facility-tabs"><Link href="/">Fleet overview</Link><Link href="/facility" aria-current="page">Facility explorer</Link></div><span className="facility-demo"><i/> Simulated environment</span></nav>
    <main className="facility-main"><div className="facility-title"><div><p className="eyebrow">GUARDFLEET / DIGITAL TWIN</p><h1>Inside your cold chain.</h1><p>Pharmaceutical distribution center · Facility A</p></div><div className="facility-summary"><span><b>20</b> assets</span><span><b style={{color:threats?"#ff7891":undefined}}>{threats}</b> threats</span><span><b style={{color:vetoes?"#ffc879":undefined}}>{vetoes}</b> safety veto</span></div></div>
    <div className="explorer-layout"><section className="explorer-view" aria-label="Interactive facility explorer"><div className="explorer-toolbar"><select aria-label="Focus room" value={room} onChange={e=>{setRoom(Number(e.target.value));setDetail(false);}}><option value={-1}>Entire facility</option>{rooms.map((r,i)=><option key={r} value={i}>{r}</option>)}</select><div className="view-modes"><button aria-pressed={mode==="solid"} onClick={()=>{setMode("solid");setDetail(false);}}>3D model</button><button aria-pressed={mode==="lidar"} onClick={()=>{setMode("lidar");setDetail(false);}}>LiDAR style</button></div><button className="reset-view" onClick={()=>{setDetail(false);setRoom(-1);setReset(r=>r+1);}}>↺ Reset view</button></div>
      <div className={`facility-canvas ${detail ? "inspection-open" : ""}`}>{detail ? <EquipmentView asset={asset} step={step} component={component} onComponent={setComponent} onBack={()=>setDetail(false)}/> : <><SceneBoundary><Scene selected={selected} step={step} mode={mode} detail={detail} room={room} reset={reset} component={component} onSelect={select} onComponent={setComponent}/></SceneBoundary><div className="scene-caption"><span>FACILITY A <b>/ {detail?selected:"OVERVIEW"}</b></span><small>{mode==="lidar"?"350k surface samples · CC0 facility assets":"Imported warehouse + industrial pipework · cutaway"}</small></div><div className="scene-help">Drag to orbit · Scroll to zoom · Right-drag to pan</div><div className="scene-legend"><span><i style={{background:"#6be4cf"}}/>Nominal</span><span><i style={{background:"#ff6785"}}/>Threat</span><span><i style={{background:"#ffc879"}}/>Safety veto</span></div></>}</div>
      <div className="asset-strip"><div><b>Asset inventory</b><small>Select a unit to inspect it</small></div><div className="asset-buttons">{assets.filter(a=>room<0||a.room===room).map(a=><button key={a.id} aria-pressed={selected===a.id} onClick={()=>select(a.id)}><i style={{background:telemetry(a,step).color}}/>{a.id}</button>)}</div></div>
    </section>
    <aside className="inspector"><div className="inspector-kicker">EQUIPMENT INSPECTOR <span>SIMULATED</span></div><h2>{asset.id} <span>Refrigeration unit</span></h2><p className="asset-location">{rooms[asset.room]} · {asset.product}</p><div className="equipment-status" style={{color:state.color}}><i style={{background:state.color}}/>{state.status}</div><button className="inspect-button" onClick={()=>{setDetail(d=>!d);setRoom(-1);}}>{detail?"↖ Return to facility":"⌖ Inspect components"}</button>
      <div className="equipment-metrics"><div><span>Temperature</span><strong style={{color:state.temperature>8?"#ff7891":undefined}}>{state.temperature.toFixed(1)}<small>°C</small></strong></div><div><span>Firmware</span><strong className="firmware">{asset.firmware}</strong></div></div><dl className="equipment-facts"><div><dt>Security status</dt><dd>{state.attacked||state.related?"Suspicious":"No alerts"}</dd></div><div><dt>Relay state</dt><dd style={{color:state.veto?"#ffc879":undefined}}>{state.relay}</dd></div><div><dt>Safety controller</dt><dd>Independent Arduino</dd></div></dl>
      <h3 className="inspector-section">Physical components</h3><div className="component-list">{["Temperature sensor","Network Pico","Safety Arduino","Control relay"].map((name,i)=><button key={name} aria-pressed={component===name} onClick={()=>{setComponent(name);setDetail(true);setRoom(-1);}}><span>0{i+1}</span>{name}<span>↗</span></button>)}</div>
      <section className="sensor-inspection"><div className="sensor-heading"><h3>{component}</h3><span>DEMO</span></div>{component==="Temperature sensor" ? <><div className="sensor-subtitle">Illustrative temperature history · °C</div><svg viewBox="0 0 280 108" role="img" aria-label={`Simulated temperature trend ending at ${state.temperature.toFixed(1)} degrees Celsius`}><rect x="0" y="28" width="280" height="60" fill="#6be4cf0b"/><line x1="0" x2="280" y1="28" y2="28" stroke="#557b74" strokeDasharray="3 5"/><text x="255" y="23" fill="#7c9993" fontSize="9">8°C</text><polyline points={state.readings.map((v,i)=>`${i*40},${108-v*10}`).join(" ")} fill="none" stroke={state.temperature>8?"#ff7891":"#6be4cf"} strokeWidth="2"/></svg><div className="sensor-values"><span>Demo baseline<b>{asset.baseline.toFixed(1)}°C</b></span><span>Anomaly score<b>{state.anomaly.toFixed(2)}</b></span></div><p>Illustrative operating band: 2–8°C. Product-specific limits will be configured with real inventory.</p></> : <><p>{component==="Network Pico"?"Network-facing controller receives remote commands. It cannot bypass the independent safety controller.":component==="Safety Arduino"?"Independent controller evaluates local sensor readings and can veto unsafe commands.":"Control relay isolates the remote actuator command path when the safety controller intervenes."}</p><div className="component-state">{component==="Network Pico"?(state.attacked?"Unauthorized command detected":"Command channel nominal"):state.veto?"Safety veto active · relay open":"Safety monitoring active"}</div></>}</section><p className="simulation-note">Illustrative values only. No live telemetry or physical devices are connected.</p>
    </aside></div>
    <section className="attack-replay"><div className="replay-heading"><div><p className="eyebrow">CYBER → PHYSICAL → SAFETY</p><h2>Watch the safety layer intervene.</h2><p>A simulated attack on FR-08, from compromise to independent isolation.</p></div><div className="replay-actions"><button onClick={()=>{if(step===4){stage(0);}setPlaying(p=>!p);}}>{playing?"Ⅱ Pause replay":step===4?"↻ Replay again":"▶ Play attack replay"}</button><button className="replay-reset" onClick={()=>stage(0)}>Reset</button></div></div><div className="replay-timeline">{replaySteps.map((event,i)=><button key={event.title} className={step===i?"current":step>i?"completed":""} aria-pressed={step===i} onClick={()=>stage(i)}><small>{event.time}</small><span><b>0{i+1}</b>{event.title}</span></button>)}</div><div className="replay-event" aria-live="polite"><span style={{color:step>=3?"#ffc879":"#c2a3f1"}}>●</span><b>{replaySteps[step].title}</b><p>{replaySteps[step].detail}</p></div></section>
    <footer><span>GuardFleet · Pharmaceutical cold chain</span><span>Adapted CC0 geometry · Simulated telemetry · <a href="/models/facility/CREDITS.md" target="_blank" rel="noreferrer">Asset credits ↗</a></span></footer></main>
  </div>;
}
