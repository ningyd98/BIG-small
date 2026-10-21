import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import JSZip from '/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/jszip/lib/index.js';

const root='/home/ningyd/文档/ChatGPT/BIGsmall';
const workspaceDir=path.join(root,'output/doc/20261021-proposal-revision');
const buildDir=path.join(workspaceDir,'.build');
await fs.mkdir(buildDir,{recursive:true});
const revisions=JSON.parse(await fs.readFile('/tmp/bigsmall-proposal-edit-20261021/revisions.json','utf8'));
const source='/home/ningyd/.codex/attachments/2b6bf4ca-a4be-4c14-a527-04a760a46b51/开题报告.pptx';
const sourceBytes=await fs.readFile(source);
const zip=await JSZip.loadAsync(sourceBytes);
const modifications=[];
const escapeXml=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const decode=s=>s.replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&quot;','"').replaceAll('&apos;',"'").replaceAll('&amp;','&');
const stripText=s=>s.replace(/(<a:t(?:\s[^>]*)?>)[\s\S]*?(<\/a:t>)/g,'$1$2');
for(const [slide,changes] of Object.entries(revisions.slides)){
  const member=`ppt/slides/slide${slide}.xml`;
  const before=await zip.file(member).async('string');
  let index=0;
  const used=new Set();
  const after=before.replace(/<a:p(?:\s[^>]*)?>[\s\S]*?<\/a:p>/g,paragraph=>{
    const current=index++;
    if(!(String(current) in changes))return paragraph;
    const replacement=changes[String(current)];
    const old=[...paragraph.matchAll(/<a:t(?:\s[^>]*)?>([\s\S]*?)<\/a:t>/g)].map(m=>decode(m[1])).join('');
    if(!old)throw new Error(`No source text ${slide}/${current}`);
    let n=0;
    const updated=paragraph.replace(/(<a:t(?:\s[^>]*)?>)[\s\S]*?(<\/a:t>)/g,(_m,a,b)=>a+((n++===0)?escapeXml(replacement):'')+b);
    modifications.push({slide:Number(slide),paragraph:current,before:old,after:replacement});
    used.add(String(current));
    return updated;
  });
  if(used.size!==Object.keys(changes).length)throw new Error(`Missing target on slide ${slide}`);
  if(stripText(before)!==stripText(after))throw new Error(`Non-text mutation ${member}`);
  zip.file(member,after);
}
const candidate=path.join(buildDir,'candidate.pptx');
await fs.writeFile(candidate,await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));
const original=await JSZip.loadAsync(sourceBytes);
const output=await JSZip.loadAsync(await fs.readFile(candidate));
const changedParts=[];
for(const member of Object.keys(original.files)){
  if(original.files[member].dir)continue;
  const a=await original.file(member).async('nodebuffer');
  const b=await output.file(member).async('nodebuffer');
  if(!a.equals(b)){
    changedParts.push(member);
    if(!/^ppt\/slides\/slide\d+\.xml$/.test(member))throw new Error('Unexpected package change '+member);
    if(stripText(a.toString())!==stripText(b.toString()))throw new Error('Structural change '+member);
  }
}
const manifest={source,sourceSha256:crypto.createHash('sha256').update(sourceBytes).digest('hex'),slideCount:12,nonTextPartsPreserved:true,changedParts,modifications};
await fs.writeFile(path.join(buildDir,'pptx-change-map.json'),JSON.stringify(manifest,null,2));
console.log(JSON.stringify({candidate,changedParagraphs:modifications.length,changedParts,allNonTextPreserved:true}));
