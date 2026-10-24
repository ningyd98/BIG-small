import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {importRuntimeModule} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs';
const {FileBlob,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const dir=path.dirname(fileURLToPath(import.meta.url));
const input='/home/ningyd/.codex/attachments/9fe2531b-6c89-4fa8-b3ca-a3037f129e75/开题报告.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const inspection=await p.inspect({select:'$.slides[*]',include:['id','index','layout','title','elements.id','elements.kind','elements.text','elements.position','elements.style','notes.text']});
await fs.writeFile(path.join(dir,'evidence','source-artifact-inspection.json'),JSON.stringify(inspection,null,2));
for(let i=0;i<p.slides.items.length;i++){
 const layout=await p.slides.items[i].export({format:'layout'});
 await fs.writeFile(path.join(dir,'evidence',`source-slide-${i+1}-layout.json`),JSON.stringify(layout,null,2));
}
const pp=await PresentationFile.exportPptx(p);
await pp.save(path.join(dir,'source-roundtrip.pptx'));
const reread=await PresentationFile.importPptx(await FileBlob.load(path.join(dir,'source-roundtrip.pptx')));
await fs.mkdir(path.join(dir,'source-roundtrip-render'),{recursive:true});
for(let i=0;i<reread.slides.items.length;i++){
 const blob=await reread.export({slide:reread.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(dir,'source-roundtrip-render',`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
console.log(JSON.stringify({status:'exported_and_rendered',slides:reread.slides.items.length,inspection:path.join(dir,'evidence','source-artifact-inspection.json')}));
