import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {importRuntimeModule} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs';
const {FileBlob,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const dir=path.dirname(fileURLToPath(import.meta.url));
const input='/home/ningyd/.codex/attachments/52bdb7c0-6fb9-47f1-b144-d55b6547a865/开题报告-宁业栋-结构重写.pptx';
const bytes=await fs.readFile(input);
const sha256=createHash('sha256').update(bytes).digest('hex');
if(sha256!=='326974f3c9926b4578b77e508f6893fcc290b6da0061423e98f66511382c7b98')throw Error('Input fingerprint changed');
await fs.mkdir(path.join(dir,'evidence'),{recursive:true});
await fs.mkdir(path.join(dir,'source-render'),{recursive:true});
await fs.mkdir(path.join(dir,'../source'),{recursive:true});
const frozenInput=path.resolve(dir,'../source/开题报告-用户修订原件.pptx');
await fs.writeFile(frozenInput,bytes);
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const layouts=[];
for(let i=0;i<p.slides.items.length;i++){
 const slide=p.slides.items[i];
 const layout=await slide.export({format:'layout'});
 layouts.push({slide:i+1,layout});
 const png=await p.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(dir,'source-render',`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
await fs.writeFile(path.join(dir,'evidence/source-layouts.json'),JSON.stringify(layouts,null,2));
await fs.writeFile(path.join(dir,'evidence/input.json'),JSON.stringify({path:input,frozenInput,sha256,bytes:bytes.length,slides:p.slides.items.length,fontFamilies:['Arial','微软雅黑','黑体']},null,2));
console.log(JSON.stringify({status:'source_inspected',sha256,slides:layouts.length,renderDir:path.join(dir,'source-render')}));
