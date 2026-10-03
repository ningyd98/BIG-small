const fs=require('fs');
const path=require('path');
const {createRequire}=require('module');
const runtimeRequire=createRequire('/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp/package.json');
const sharp=runtimeRequire('sharp');
function frame(h){return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${h}" viewBox="0 0 1200 ${h}"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#303030"/></marker></defs><rect width="1200" height="${h}" fill="white"/><g font-family="Noto Sans CJK SC, sans-serif" fill="#111111">`;}
function text(x,y,lines,size=29){return `<text x="${x}" y="${y}" text-anchor="middle" font-size="${size}">${lines.map((l,i)=>`<tspan x="${x}" dy="${i===0?0:size+10}">${l}</tspan>`).join('')}</text>`;}
function box(x,y,w,h,lines,size=29){const ty=y+h/2-((lines.length-1)*(size+10))/2+size*.32;return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="#f6f6f6" stroke="#666" stroke-width="2"/>${text(x+w/2,ty,lines,size)}`;}
function line(x1,y1,x2,y2,dash=false){return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#303030" stroke-width="2.6" ${dash?'stroke-dasharray="8 6"':''} marker-end="url(#arrow)"/>`;}
function poly(points,dash=false){return `<polyline points="${points}" fill="none" stroke="#303030" stroke-width="2.6" ${dash?'stroke-dasharray="8 6"':''} marker-end="url(#arrow)"/>`;}
async function save(name,svg){fs.writeFileSync(path.join(__dirname,name+'.svg'),svg);await sharp(Buffer.from(svg)).resize({width:2400}).png().toFile(path.join(__dirname,name+'.png'));}
(async()=>{
let a=frame(945)+text(600,40,['在线验证驱动的执行决策闭环'],32);
a+=box(70,80,1060,86,['同一后端与 episode：RGB-D 新帧、标定、关节与执行反馈'],28);
a+=line(600,166,600,201);
a+=box(230,207,740,90,['VLM 像素理解 + 原始深度几何解算','校准风险、动作时效、任务与版本状态'],28);
a+=line(400,297,230,344)+line(800,297,890,344);
a+=box(50,350,475,126,['C1 有限候选决策','继续 / 重观测 / 本地恢复','云端求助 / 停止'],28);
a+=box(675,350,475,126,['云端慢规划与复杂重规划','返回受约束候选','边缘保留最终拒绝权'],28);
a+=line(530,398,669,398)+line(670,443,533,443);
a+=line(286,476,286,518);
a+=box(50,525,475,103,['C2 证据契约与局部修复','提交前复核 + SafetyShield'],28);
a+=line(531,576,669,576);
a+=box(675,525,475,103,['确定性物理技能','actuator / step + 实际启动回执'],26);
a+=line(910,628,910,672);
a+=box(675,679,475,108,['动作后新观测与在线效果验证','PASS / FAIL / UNKNOWN','最终验证失败仍进入有界恢复'],25);
a+=poly('675,732 20,732 20,125 63,125')+text(305,710,['步骤结果与证据失效反馈'],25);
a+=box(60,835,1080,77,['独立评价器：事后核验物理成功与误报完成；真值不回流在线决策'],27);
a+=poly('1160,576 1180,576 1180,873 1145,873',true);
a+='</g></svg>';await save('architecture',a);
let h=frame(760)+text(600,42,['局部修复的生命周期与验证出口'],32);
const hx=[40,450,860];
h+=box(hx[0],92,300,114,['PREPARED','候选准备','无运动权限'],29);
h+=box(hx[1],92,300,114,['EDGE_ACCEPTED','边缘真实接受','回执可追溯'],27);
h+=box(hx[2],92,300,114,['ACTIVATED','提交前再次复核','版本条件原子激活'],27);
h+=line(345,149,442,149)+line(755,149,852,149);
h+=line(1010,206,1010,283);
h+=box(860,290,300,124,['EXECUTION_STARTED','必要时显式恢复','实际执行器已启动'],24);
h+=box(450,290,300,124,['在线效果验证','动作后新观测','PASS / FAIL / UNKNOWN'],23);
h+=box(40,290,300,124,['PASS','确认恢复效果','关闭原事件'],29);
h+=line(852,352,758,352)+line(442,352,348,352);
h+=line(600,414,600,480);
h+=box(210,487,780,97,['UNKNOWN → 有限重观测；可恢复 FAIL → 重新修复','硬故障、无进展或预算耗尽 → 明确停止或失败'],28);
h+=poly('210,512 15,512 15,149 34,149',true)+text(110,484,['预算内可恢复'],22);
h+=text(600,648,['重试与重观测预算跨事件保留；新帧或新 ID 不自动清零'],28);
h+=text(600,702,['已完成不可重复动作不重放；独立评价不决定在线恢复'],28)+'</g></svg>';await save('handover',h);
let e=frame(755)+text(600,42,['当前基础与十二周研究验证路线'],32);
e+=text(600,83,['已完成 P1：来源审计与同步 RGB-D；模型与物理抓放待验收'],26);
const r1=[['W1—W4 基础闭环','数据 / VLM / 物理技能','三值验证与事件路由'],['W4 基础先导','120 场景 / 超时与预算','G0、G1 初检与成本账本'],['W5—W8 方法与对照','C1 决策 / C2 门控修复','公平 B0—B4 与消融']];
for(let i=0;i<3;i++){e+=box(20+i*405,123,350,150,r1[i],28);if(i<2)e+=line(375+i*405,198,419+i*405,198);}
e+=line(1005,273,1005,357);
const r2=[['W12 论文与复现包','目标逐项核验 / 失败边界','原始记录重建全部图表'],['W10—W11 配对统计','主比较至少 600 场景','G4 另用 200 故障'],['W9 配对先导锁 N','另 120 场景 / 协议 hash','W10 正式实验']];
for(let i=0;i<3;i++){e+=box(20+i*405,363,350,150,r2[i],28);if(i>0)e+=line(420+(i-1)*405,438,377+(i-1)*405,438);}
e+=box(65,563,1070,94,['可选扩展：Jev 判断器 / G5 定向采样 / Isaac / 技能缓存','先完成 C1/C2；扩展不阻塞核心结论'],28);
e+=text(600,705,['两轮先导与测试互斥；实际开发按依赖推进，不等待周次'],27)+'</g></svg>';await save('experiment',e);
console.log(JSON.stringify({figures:3,directory:__dirname}));
})().catch(e=>{console.error(e);process.exit(1);});
