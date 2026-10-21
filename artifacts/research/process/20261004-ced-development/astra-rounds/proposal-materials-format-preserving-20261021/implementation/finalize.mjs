import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import JSZip from '/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/jszip/lib/index.js';
import { finalizePresentation } from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/artifact_tool_utils.mjs';
const workspaceDir='/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision';
const buildDir=path.join(workspaceDir,'.build');
const source='/home/ningyd/.codex/attachments/2b6bf4ca-a4be-4c14-a527-04a760a46b51/开题报告.pptx';
const data=await fs.readFile(source);
const zip=await JSZip.loadAsync(data);
const families=new Set();
for(const name of Object.keys(zip.files)){
 if(/^ppt\/slides\/slide\d+\.xml$/.test(name)){
  for(const m of (await zip.file(name).async('string')).matchAll(/typeface="([^"]+)"/g))if(!m[1].startsWith('+'))families.add(m[1]);
 }
}
const skill='/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const result=await finalizePresentation({
 workspaceDir,candidatePath:path.join(buildDir,'candidate.pptx'),finalPath:path.join(workspaceDir,'开题报告_修改版.pptx'),
 explicitTotalSlideCount:12,
 pythonExecutable:'/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 fontPolicy:{basis:'reference',families:[...families],referencePath:source,referenceSha256:crypto.createHash('sha256').update(data).digest('hex')},
 verifyArtifactToolImport:true,
 receiptPath:path.join(buildDir,'pptx-validation.json')
});
console.log(JSON.stringify(result));
