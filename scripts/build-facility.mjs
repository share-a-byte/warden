// Rebuild from CC0 source assets downloaded to work/facility-assets. See public/models/facility/CREDITS.md.
import fs from 'node:fs';
import * as T from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
function glb(json,bin){
 const text=Buffer.from(JSON.stringify(json));const padded=Buffer.alloc(Math.ceil(text.length/4)*4,32);text.copy(padded);
 const data=Buffer.alloc(Math.ceil(bin.length/4)*4);bin.copy(data);
 const head=Buffer.alloc(20);head.writeUInt32LE(0x46546c67);head.writeUInt32LE(2,4);head.writeUInt32LE(28+padded.length+data.length,8);head.writeUInt32LE(padded.length,12);head.writeUInt32LE(0x4e4f534a,16);
 const bh=Buffer.alloc(8);bh.writeUInt32LE(data.length);bh.writeUInt32LE(0x004e4942,4);return Buffer.concat([head,padded,bh,data]);
}
function strip(j){delete j.images;delete j.textures;delete j.samplers;j.materials=[{pbrMetallicRoughness:{baseColorFactor:[.4,.5,.6,1]}}];for(const m of j.meshes)for(const p of m.primitives)p.material=0;return j;}
async function load(path,isGLB){let j,bin;if(isGLB){const b=fs.readFileSync(path);const n=b.readUInt32LE(12);j=JSON.parse(b.subarray(20,20+n));bin=b.subarray(28+n);}else{j=JSON.parse(fs.readFileSync(path));bin=fs.readFileSync('work/facility-assets/pipes/'+j.buffers[0].uri);delete j.buffers[0].uri;}
 const b=glb(strip(j),bin);return (await new GLTFLoader().parseAsync(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength),'' )).scene;
}
const parts=[];
function add(geo,pos=[0,0,0],scale=[1,1,1],color='#516f7d',rotation=[0,0,0]){
 let g=geo.index?geo.toNonIndexed():geo.clone();for(const key of Object.keys(g.attributes))if(!['position','normal'].includes(key))g.deleteAttribute(key);if(!g.attributes.normal)g.computeVertexNormals();
 const m=new T.Matrix4().compose(new T.Vector3(...pos),new T.Quaternion().setFromEuler(new T.Euler(...rotation)),new T.Vector3(...scale));g.applyMatrix4(m);
 const c=new T.Color(color),v=new Float32Array(g.attributes.position.count*3);for(let i=0;i<v.length;i+=3){v[i]=c.r;v[i+1]=c.g;v[i+2]=c.b;}g.setAttribute('color',new T.BufferAttribute(v,3));parts.push(g);
}
function box(p,s,c){add(new T.BoxGeometry(...s),p,[1,1,1],c);}
function pipe(a,b,r=.1,c='#5d8493'){const d=new T.Vector3(...b).sub(new T.Vector3(...a));const q=new T.Quaternion().setFromUnitVectors(new T.Vector3(0,1,0),d.clone().normalize());const g=new T.CylinderGeometry(r,r,d.length(),12);g.applyQuaternion(q);add(g,new T.Vector3(...a).add(new T.Vector3(...b)).multiplyScalar(.5).toArray(),[1,1,1],c);}
const warehouse=await load('work/facility-assets/warehouse.glb',true);warehouse.updateMatrixWorld(true);
warehouse.traverse(o=>{if(!o.isMesh)return;let g=o.geometry.index?o.geometry.toNonIndexed():o.geometry.clone();g.applyMatrix4(o.matrixWorld);g.computeBoundingBox();const bounds=g.boundingBox,center=bounds.getCenter(new T.Vector3());
 const coords=[],normals=[];const p=g.attributes.position,n=g.attributes.normal;
 for(let i=0;i<p.count;i+=3){const tri=[0,1,2].map(k=>new T.Vector3().fromBufferAttribute(p,i+k));const normalized=tri.map(v=>new T.Vector3((v.x-center.x)*1.3,(v.y-bounds.min.y)*.8,(v.z-center.z)*.46));
 // Remove roof and the front facade for an unobstructed cutaway.
 if(normalized.reduce((sum,v)=>sum+v.y,0)/3>4.9||normalized.every(v=>v.z>10.8))continue;
 for(let k=0;k<3;k++){coords.push(...normalized[k].toArray());normals.push(n.getX(i+k),n.getY(i+k),n.getZ(i+k));}}
 const out=new T.BufferGeometry();out.setAttribute('position',new T.Float32BufferAttribute(coords,3));out.setAttribute('normal',new T.Float32BufferAttribute(normals,3));add(out,[1,0,-1],[1,1,1],'#415364');});
const kit=await load('work/facility-assets/pipes/pipes.gltf',false);const modules=[];kit.traverse(o=>{if(o.isMesh){const g=o.geometry.clone();g.center();g.computeBoundingBox();modules.push(g);}});
// Steel frame, open roof trusses, cable trays, and central service pipework.
for(const x of [-13,-4.5,4.5,15])for(const z of [-10,-4,3,10]){box([x,2.8,z],[.18,5.6,.22],'#71848e');box([x,5.65,z],[.65,.16,.4],'#70828d');}
for(const z of [-10,-4,3,10]){box([1,5.7,z],[28,.16,.16],'#617889');for(let x=-13;x<15;x+=3.5){pipe([x,5.7,z],[x+1.75,6.5,z],.045);pipe([x+1.75,6.5,z],[x+3.5,5.7,z],.045);}}
for(const x of [-11.7,-2.7,6.3]){box([x,4.9,-.4],[.8,.35,20],'#8a9ba4');for(let z=-10;z<10;z+=.45)box([x,4.9,z],[.85,.04,.04],'#b2bfc4');}
for(let i=0;i<4;i++){pipe([-12,4.4+i*.3,-9],[14,4.4+i*.3,-9],.09,'#498fa1');for(const x of [-9,0,9]){pipe([x,4.4+i*.3,-9],[x,1,-9],.07,'#518994');add(modules[(i+3)%modules.length],[x,1.5+i*.5,-9],[1.5,1.5,1.5],'#719ca9');}}
// Mechanical annex: detailed imported valves and pipe assemblies, tanks, pumps, access gantry.
for(let i=0;i<5;i++){const x=-10+i*4.8;add(new T.CylinderGeometry(.8,.8,3,24),[x,1.8,-7.6],[1,1,1],'#77929c');add(new T.SphereGeometry(.8,20,12),[x,3.3,-7.6],[1,.45,1],'#77929c');for(const dx of [-.6,.6])box([x+dx,.25,-7.6],[.15,.5,.8],'#566b77');pipe([x,3.6,-7.6],[x,4.3,-7.6],.14);pipe([x,4.3,-7.6],[x,4.3,-9],.14);add(modules[4],[x+1.3,.8,-7.4],[2,2,2],'#67969e');add(modules[7],[x+1.3,1.6,-7.4],[1.8,1.8,1.8],'#9d8d66');}
// Pallet racking and packages in dispatch zone, kept clear of selectable refrigerators.
for(const x of [-12,14])for(const z of [-2,3,7]){for(const dx of [-.65,.65])for(const dz of [-1,1])box([x+dx,1.8,z+dz],[.07,3.6,.07],'#658ba2');for(const y of [.3,1.35,2.4,3.45]){box([x,y,z],[1.4,.08,2.2],'#a88b58');if(y<3)for(const dz of [-.55,.55]){box([x,y+.35,z+dz],[1.1,.6,.9],'#7b8490');box([x,y+.36,z+dz+.46],[.22,.24,.01],'#c7d9d5');}}}
// Staging conveyor, roller beds, ventilation units and protected service walkway.
for(let x=-10;x<12;x+=1.5){pipe([x,.8,7],[x,.8,8.6],.1,'#93a6af');box([x,.4,7.2],[.08,.8,.08],'#647e8e');}
for(const z of [7,8.6])box([1,.75,z],[25,.18,.12],'#5c778b');
for(const x of [-8,1,10]){box([x,5,-5.8],[2.8,.9,1.3],'#617981');for(let i=0;i<14;i++)box([x-1.2+i*.18,4.9,-5.12],[.04,.55,.04],'#b8ccd1');}
for(const x of [-4.5,4.5]){box([x,1.45,0],[.07,2.9,12],'#2b4653');box([x,3,0],[.12,.15,12],'#7993a5');}
const geometry=mergeGeometries(parts);geometry.computeBoundingBox();const mesh=new T.Mesh(geometry,new T.MeshStandardMaterial());
// Deterministic area-weighted sampling creates an actual point representation of the imported surfaces.
let seed=817;const random=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
const sampler=new MeshSurfaceSampler(mesh).setRandomGenerator(random).build();const count=350000,positions=new Float32Array(count*3),colors=new Float32Array(count*3);const v=new T.Vector3(),normal=new T.Vector3(),color=new T.Color();
for(let i=0;i<count;i++){sampler.sample(v,normal,color);positions.set(v.toArray(),i*3);const height=Math.max(0,Math.min(1,v.y/6.5));color.setHSL(.53-height*.34,.7,.35+random()*.16);colors.set(color.toArray(),i*3);}
fs.writeFileSync('public/models/facility/facility-points.bin',Buffer.concat([Buffer.from(positions.buffer),Buffer.from(colors.buffer)]));
// Minimal untextured glTF: vertex colors retain detail without heavyweight textures.
const attrs=['position','normal','color'];let offset=0;const chunks=[],views=[],accessors=[];
for(const name of attrs){const attribute=geometry.getAttribute(name),buf=Buffer.from(attribute.array.buffer,attribute.array.byteOffset,attribute.array.byteLength);chunks.push(buf);views.push({buffer:0,byteOffset:offset,byteLength:buf.length,target:34962});accessors.push({bufferView:views.length-1,componentType:5126,count:attribute.count,type:'VEC3',...(name==='position'?{min:geometry.boundingBox.min.toArray(),max:geometry.boundingBox.max.toArray()}:{} )});offset+=buf.length;}
const json={asset:{version:'2.0',generator:'Warden CC0 facility composition'},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0,NORMAL:1,COLOR_0:2},material:0}]}],materials:[{doubleSided:true,pbrMetallicRoughness:{metallicFactor:.25,roughnessFactor:.65}}],buffers:[{byteLength:offset}],bufferViews:views,accessors};
fs.writeFileSync('public/models/facility/facility.glb',glb(json,Buffer.concat(chunks)));
fs.writeFileSync('public/models/facility/manifest.json',JSON.stringify({points:count,triangles:geometry.attributes.position.count/3,bounds:geometry.boundingBox,source:'CC0 warehouse + Poly Haven industrial pipe kit; custom layout and fixtures'},null,2));
console.log('Built facility:',geometry.attributes.position.count/3,'triangles;',count,'points.');
