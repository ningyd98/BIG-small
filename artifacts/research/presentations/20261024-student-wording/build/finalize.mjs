import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {finalizePresentation} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/artifact_tool_utils.mjs';
const workspace='/home/ningyd/文档/ChatGPT/BIGsmall';
const dir=path.dirname(fileURLToPath(import.meta.url));
const skill='/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const input=JSON.parse(await fs.readFile(path.join(dir,'evidence/input.json'),'utf8'));
const output=path.join(workspace,'output/pptx/20261024-student-wording');
await fs.mkdir(output,{recursive:true});
const tableOwners=[4,6,8,9,10,11];
const result=await finalizePresentation({
 workspaceDir:workspace,
 candidatePath:path.join(dir,'student-wording-candidate.pptx'),
 finalPath:path.join(output,'开题报告-宁业栋-学生口吻优化.pptx'),
 pythonExecutable:'/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:12,
 requiredNativeTableOwnerSlides:tableOwners,
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--cover-role','cover','--validate-heading-fit','--validate-bullet-geometry',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],
 fontPolicy:{basis:'reference',families:input.fontFamilies,referencePath:input.frozenInput,referenceSha256:input.sha256},
 verifyArtifactToolImport:true,
 receiptPath:path.join(dir,'evidence/final-validation.json'),
});
console.log(JSON.stringify({finalPath:result.finalPath,sha256:result.finalSha256,bytes:result.byteCount,receipt:result.receiptPath}));
