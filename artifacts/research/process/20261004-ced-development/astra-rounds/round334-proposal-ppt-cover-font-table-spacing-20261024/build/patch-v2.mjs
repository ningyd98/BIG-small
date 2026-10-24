import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {importRuntimeModule} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs';
const {FileBlob,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const dir=path.dirname(fileURLToPath(import.meta.url));
const input=path.resolve(dir,'../../round332-proposal-ppt-structure-rewrite-20261024/build/rewritten-candidate.pptx');
const before=await fs.readFile(input);
if(createHash('sha256').update(before).digest('hex')!=='7a1c664f34c633afbb617e10941796999062c2f94ed05eeb4a92bf24b5a10573')throw Error('Pinned candidate changed');
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const l=await p.slides.items[0].export({format:'layout'});
const coverTargets=[{objectId:'143',text:'面向边缘智能场景的小型机械臂云边协同控制系统的设计'},{objectId:'4',text:'姓名：宁业栋\n专业：工程管理\n指导教师：康劲'}];
for(const target of coverTargets){
 const matches=l.elements.filter(e=>e.kind==='textbox'&&e.text===target.text);
 if(matches.length!==1)throw Error('Cover text anchor is not unique');
 target.anchor=matches[0].id;target.previousStyle=matches[0].style;
 p.resolve(target.anchor).text.style.typeface='微软雅黑';
}
const tableLayout=await p.slides.items[9].export({format:'layout'});
const tables=tableLayout.elements.filter(e=>e.kind==='table');
if(tables.length!==1||!tables[0].text.includes('4.3 系统实现与集成'))throw Error('Thesis table anchor changed');
const table=p.resolve(tables[0].id);
table.cells.block({row:1,column:0,rowCount:4,columnCount:2}).assign({margins:{left:12,right:12,top:8/3,bottom:8/3}});
await fs.mkdir(path.join(dir,'evidence'),{recursive:true});
const out=path.join(dir,'rewritten-candidate-v2.pptx');
await(await PresentationFile.exportPptx(p)).save(out);
await fs.writeFile(path.join(dir,'evidence/patch-generation.json'),JSON.stringify({input,inputSha256:createHash('sha256').update(before).digest('hex'),output:out,outputSha256:createHash('sha256').update(await fs.readFile(out)).digest('hex'),coverTargets,tableChanges:{slide:10,sourceObjectId:'6',anchor:tables[0].id,rows:[1,2,3,4],columns:[0,1],marginsPx:{left:12,right:12,top:8/3,bottom:8/3},otherFields:'unchanged'}},null,2));
const reread=await PresentationFile.importPptx(await FileBlob.load(out));
await fs.mkdir(path.join(dir,'render'),{recursive:true});
for(let i=0;i<reread.slides.items.length;i++){
 const s=reread.slides.items[i],blob=await reread.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(dir,'render',`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
 await fs.writeFile(path.join(dir,'evidence',`slide-${i+1}-layout.json`),JSON.stringify(await s.export({format:'layout'}),null,2));
}
console.log(JSON.stringify({status:'v2_exported_and_rendered',slides:reread.slides.items.length,path:out}));
