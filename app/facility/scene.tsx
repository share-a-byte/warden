"use client";
import { Canvas, useThree } from "@react-three/fiber";
import { Edges, OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef } from "react";
import { CanvasTexture, SRGBColorSpace } from "three";
import type { OrbitControls as OrbitControlsType } from "three-stdlib";
import { assets, rooms, telemetry, type Asset } from "./data";
import FacilityEnvironment from "./environment";

type Props = { selected: string; step: number; mode: "solid" | "lidar"; detail: boolean; room: number; reset: number; component: string; onSelect: (id: string) => void; onComponent: (id: string) => void };
function Label({ text, position, color = "#aac3d7", onClick }: { text: string; position: [number,number,number]; color?: string; onClick?: () => void }) {
  const texture = useMemo(()=>{
    const canvas=document.createElement("canvas");canvas.width=512;canvas.height=80;
    const ctx=canvas.getContext("2d")!;
    ctx.fillStyle="#0a1420";ctx.fillRect(0,0,512,80);
    ctx.strokeStyle=color;ctx.lineWidth=3;ctx.strokeRect(2,2,508,76);
    ctx.fillStyle=color;ctx.font="28px Arial";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(text,256,40);
    const map=new CanvasTexture(canvas);map.colorSpace=SRGBColorSpace;return map;
  },[text,color]);
  useEffect(()=>()=>texture.dispose(),[texture]);
  return <sprite position={position} scale={[text.length>15?3.5:1.65,.4,1]} onClick={e=>{e.stopPropagation();onClick?.();}}><spriteMaterial map={texture} transparent depthTest depthWrite={false}/></sprite>;
}
function PointBox({ size, color }: { size: [number,number,number]; color: string }) {
  const [w,h,d] = size;
  const positions = useMemo(() => {
    const p: number[] = [];
    for(let x=0;x<=14;x++) for(let y=0;y<=20;y++) for(let z=0;z<=10;z++) {
      if(x!==0 && x!==14 && y!==0 && y!==20 && z!==0 && z!==10) continue;
      p.push((x/14-.5)*w,(y/20-.5)*h,(z/10-.5)*d);
    }
    return new Float32Array(p);
  },[w,h,d]);
  return <points><bufferGeometry><bufferAttribute attach="attributes-position" args={[positions,3]} /></bufferGeometry><pointsMaterial color={color} size={.035} sizeAttenuation transparent opacity={.85}/></points>;
}
function Unit({ asset, props }: { asset: Asset; props: Props }) {
  const state = telemetry(asset,props.step), selected = props.selected===asset.id;
  return <group position={[asset.x,1.35,asset.z]}>
    <mesh onClick={e=>{e.stopPropagation();props.onSelect(asset.id);}}>
      <boxGeometry args={[1.75,2.7,1.65]}/>
      <meshStandardMaterial color={selected?"#29344e":"#192c37"} transparent opacity={props.mode==="lidar"?.055:.92} metalness={.5} roughness={.4}/>
      <Edges color={selected?"#dfc4ff":state.color} threshold={15}/>
    </mesh>
    {props.mode==="lidar" && <PointBox size={[1.75,2.7,1.65]} color={state.color}/>}
    <mesh position={[0,0,.84]}><boxGeometry args={[.025,2.35,.025]}/><meshBasicMaterial color="#648390"/></mesh>
    <mesh position={[.54,.15,.9]}><boxGeometry args={[.07,.65,.08]}/><meshStandardMaterial color="#a5bbc5"/></mesh>
    <mesh position={[.43,.9,.85]}><boxGeometry args={[.43,.2,.04]}/><meshBasicMaterial color={state.color}/></mesh>
    <Label position={[0,1.9,0]} color={state.color} text={`${asset.id}${state.veto?" / VETO":state.attacked||state.related?" / ALERT":""}`} onClick={()=>props.onSelect(asset.id)}/>

  </group>;
}
function World(props: Props) {
  const controls = useRef<OrbitControlsType>(null);
  const { camera, invalidate, size } = useThree();
  useEffect(()=>{
    const asset=assets.find(a=>a.id===props.selected)!;
    const target=props.detail ? [asset.x,1.3,asset.z] : props.room>=0 ? [-7.3+props.room*9,0,0] : [0,0,0];
    const fit=Math.max(1,1.35/(size.width/size.height));
    camera.position.set(target[0]+(props.detail?6:props.room>=0?12:24)*fit,(props.detail?6:props.room>=0?15:24)*fit,target[2]+(props.detail?8:props.room>=0?15:28)*fit);
    controls.current?.target.set(target[0],target[1],target[2]);controls.current?.update();invalidate();
  },[camera,invalidate,props.detail,props.selected,props.room,props.reset,size.width,size.height]);
  return <><color attach="background" args={["#111b23"]}/><ambientLight intensity={1.3}/><directionalLight position={[6,18,10]} intensity={2}/><pointLight position={[-10,8,-6]} color="#9c76ff" intensity={55}/>
    <gridHelper args={[48,48,"#344052","#172632"]} position={[0,-.08,0]}/>
    <Suspense fallback={null}><FacilityEnvironment mode={props.mode}/></Suspense>
    {rooms.map((name,i)=><group key={name} position={[-7.3+i*9,0,0]} visible={props.room<0 || props.room===i}><Label position={[0,.1,6]} text={`0${i+1} / ${name}`}/></group>)}
    {assets.filter(a=>props.room<0 || a.room===props.room).map(asset=><Unit key={asset.id} asset={asset} props={props}/>)}
    <OrbitControls ref={controls} makeDefault minDistance={3} maxDistance={110} minPolarAngle={.2} maxPolarAngle={Math.PI/3} enableDamping={false}/>
  </>;
}
export default function FacilityScene(props: Props) {
  return <Canvas frameloop="demand" dpr={[1,1.7]} camera={{ position:[24,24,28],fov:43,near:.1,far:150 }} fallback={<div className="scene-fallback">3D requires WebGL. Use the asset list to inspect all equipment.</div>}><World {...props}/></Canvas>;
}
