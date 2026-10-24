"use client";
import { useLoader } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import { FileLoader } from "three";
import { useMemo } from "react";

export default function FacilityEnvironment({ mode }: { mode: "solid" | "lidar" }) {
  const { scene } = useGLTF("/models/facility/facility.glb");
  const buffer = useLoader(FileLoader, "/models/facility/facility-points.bin", loader => loader.setResponseType("arraybuffer")) as ArrayBuffer;
  const cloud = useMemo(() => {
    const count = buffer.byteLength / 24;
    return { positions: new Float32Array(buffer, 0, count * 3), colors: new Float32Array(buffer, count * 12, count * 3) };
  }, [buffer]);
  return <group>
    <primitive object={scene} visible={mode === "solid"} />
    <points visible={mode === "lidar"} raycast={() => {}}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[cloud.positions,3]} /><bufferAttribute attach="attributes-color" args={[cloud.colors,3]} /></bufferGeometry>
      <pointsMaterial vertexColors size={.045} sizeAttenuation transparent opacity={.85} depthWrite={false} />
    </points>
  </group>;
}
