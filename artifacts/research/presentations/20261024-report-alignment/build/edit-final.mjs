import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {importRuntimeModule} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs';
const {FileBlob,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const dir=path.dirname(fileURLToPath(import.meta.url));
const input=JSON.parse(await fs.readFile(path.join(dir,'evidence/input.json'),'utf8'));
const bytes=await fs.readFile(input.frozenInput);
if(createHash('sha256').update(bytes).digest('hex')!==input.sha256)throw Error('Frozen input changed');
const edits=JSON.parse(await fs.readFile(path.join(dir,'edits-final.json'),'utf8'));
const p=await PresentationFile.importPptx(await FileBlob.load(input.frozenInput));
if(p.slides.items.length!==12)throw Error('Unexpected source slide count');
const sourceLayouts=[];
for(const slide of p.slides.items)sourceLayouts.push(await slide.export({format:'layout'}));
const receipt={input,changes:[],notes:edits.notes,sourceDesign:'12 slides, existing images, logos, theme, masters, tables and source type sizes retained'};
for(const edit of edits.textboxes){
 const matches=sourceLayouts[edit.slide-1].elements.filter(e=>e.kind==='textbox'&&e.text===edit.old);
 if(matches.length!==1)throw Error(`Text anchor not unique on slide ${edit.slide}`);
 const e=matches[0],shape=p.resolve(e.id);
 shape.text=edit.text;
 shape.text.style={...e.style};
 if(edit.height)shape.position={...e.position,height:edit.height};
 receipt.changes.push({...edit,anchor:e.id,originalStyle:e.style,originalPosition:e.position});
}
for(const edit of edits.tables){
 const matches=sourceLayouts[edit.slide-1].elements.filter(e=>e.kind==='table');
 if(matches.length!==1)throw Error(`Table anchor not unique on slide ${edit.slide}`);
 const table=p.resolve(matches[0].id);
 for(let r=0;r<edit.values.length;r++)for(let c=0;c<edit.values[r].length;c++){
  table.cells.set(r,c,edit.values[r][c]);
  const fontSize=edit.slide===10?(r===0?25:64/3):edit.slide===9?24:edit.slide===11&&r>0&&c===2?24:26;
  table.getCell(r,c).text.style={typeface:'微软雅黑',fontSize,bold:r===0,color:r===0?'#FFFFFF':'#202020',alignment:edit.slide===6||(edit.slide===10&&r===0)?'center':'left'};
 }
 receipt.changes.push({slide:edit.slide,anchor:matches[0].id,kind:'table',before:matches[0].text,values:edit.values,position:matches[0].position});
}
for(const add of edits.additions){
 const slide=p.slides.items[add.slide-1];
 const shape=slide.shapes.add({geometry:'textbox',position:add.position,fill:'none',line:{style:'solid',fill:'none',width:0}});
 shape.text=add.text;
 shape.text.style={...add.style};
 receipt.changes.push({...add,kind:'newTextbox',anchor:shape.id});
}
await fs.writeFile(path.join(dir,'evidence/source-final-layouts.json'),JSON.stringify(sourceLayouts,null,2));
for(const n of edits.notes)p.slides.items[n.slide-1].speakerNotes.text=n.text;
const candidate=path.join(dir,'report-alignment-candidate-final.pptx');
await(await PresentationFile.exportPptx(p)).save(candidate);
receipt.candidate=candidate;
receipt.sha256=createHash('sha256').update(await fs.readFile(candidate)).digest('hex');
const reread=await PresentationFile.importPptx(await FileBlob.load(candidate));
await fs.mkdir(path.join(dir,'render-final'),{recursive:true});
const finalLayouts=[];
for(let i=0;i<reread.slides.items.length;i++){
 const slide=reread.slides.items[i];
 const png=await reread.export({slide,format:'png',scale:1});
 await fs.writeFile(path.join(dir,'render-final',`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
 finalLayouts.push({slide:i+1,layout:await slide.export({format:'layout'})});
}
await fs.writeFile(path.join(dir,'evidence/edit-final-receipt.json'),JSON.stringify(receipt,null,2));
await fs.writeFile(path.join(dir,'evidence/candidate-final-layouts.json'),JSON.stringify(finalLayouts,null,2));
console.log(JSON.stringify({status:'edited_and_rendered',candidate,sha256:receipt.sha256,slides:reread.slides.items.length}));
