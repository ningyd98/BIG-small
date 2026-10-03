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
let a=frame(870)+text(600,42,['真实 RGB-D 观测驱动的云边协同闭环'],32);
a+=box(70,80,1060,93,['RGB / 原始深度 / 有效掩码 / 标定 / 观测时间与版本'],29);
a+=line(330,173,330,215)+line(870,173,870,215);
a+=box(70,220,515,107,['真实本地 VLM：图片 → 像素目标','RGB 与深度可视化辅助理解'],29);
a+=box(635,220,495,107,['几何计算：原始深度 + 标定','像素反投影 → 世界坐标'],29);
a+=line(590,270,630,270);
a+=line(330,327,480,377)+line(870,327,720,377);
a+=box(190,383,820,93,['视觉证据：校准误差界 / 运动界 / 信息年龄','不确定或失效证据触发重观测或停止'],29);
a+=poly('350,476 200,515 200,545')+poly('800,476 600,515 600,545');
a+=box(20,550,350,107,['C1 联合决策','继续 / 重观测 / 云求助','本地恢复 / 停止'],25);
a+=box(425,550,350,107,['C2 证据契约门控','版本与几何复核 / 修复'],27);
a+=box(830,550,350,107,['SafetyShield 与物理技能','MuJoCo actuator / step'],27);
a+=line(375,603,420,603)+line(780,603,825,603);
a+=box(490,715,630,82,['独立结果判定：接触、提升、稳定放置'],29)+poly('1000,657 1000,709');
a+=poly('1140,657 1140,686 8,686 8,127 65,127',true)+text(245,754,['设备观测与事件反馈'],25);
a+=text(600,843,['真值仅供离线教师与独立评价；在线策略不得读取目标真值'],27)+'</g></svg>';await save('architecture',a);
let h=frame(810)+box(55,20,240,64,['云端规划系统'])+box(450,20,360,64,['边缘证据与安全层'])+box(940,20,240,64,['MuJoCo 物理执行'],24);
h+=line(175,95,175,735,true)+line(630,95,630,735,true)+line(1060,95,1060,735,true);
h+=line(175,145,620,145)+text(400,126,['候选补丁 + 观测 ID + 版本'],27);
h+=box(420,185,420,108,['首次验证：证据与依赖一致','UNKNOWN → 重观测或停止'],28);
h+=line(640,350,1050,350)+text(850,330,['旧计划有效时继续 否则安全暂停'],23);
h+=line(1060,425,640,425)+text(850,407,['安全边界处采集新观测'],27);
h+=box(420,463,420,116,['提交前复核：误差界与时效','版本一致 + SafetyShield 通过'],28);
h+=line(640,630,1050,630)+text(850,610,['原子提交未完成依赖后缀'],27);
h+=line(620,705,185,705)+text(400,685,['提交 ACK 或可追溯拒绝原因'],27);
h+=text(600,785,['已完成物理效果须新观测确认；不可重复动作不得再次提交'],28)+'</g></svg>';await save('handover',h);
let e=frame(690)+text(600,42,['十二周研究协议与独立证据链'],32);
const r1=[['W1—W4 真实闭环','RGB-D / VLM / 物理执行','通过 G0 与 G1 初检'],['W4 基础先导','120 场景 / 超时与预算','锁场景池及样本规则'],['W5—W8 方法与对照','C1 决策 / C2 门控修复','公平 B0—B4 与消融']];
for(let i=0;i<3;i++){e+=box(20+i*405,90,350,150,r1[i],28);if(i<2)e+=line(375+i*405,165,419+i*405,165);}
e+=line(1005,240,1005,324);
const r2=[['W12 论文与复现包','目标逐项核验 / 失败边界','原始记录重建全部图表'],['W10—W11 配对统计','主比较至少 600 场景','G4 另用 200 故障'],['W9 配对先导锁 N','另 120 场景 / 协议 hash','W10 正式实验']];
for(let i=0;i<3;i++){e+=box(20+i*405,330,350,150,r2[i],28);if(i>0)e+=line(420+(i-1)*405,405,377+(i-1)*405,405);}
e+=box(65,542,1070,90,['资源允许的扩展：G5 定向采样 / Isaac 跨引擎 / 技能缓存','扩展不阻塞 MuJoCo 核心结论，全部失败与 BLOCKED 保留'],28);
e+=text(600,670,['两轮各 120 个先导场景均不进入正式测试；测试按组隔离'],27)+'</g></svg>';await save('experiment',e);
console.log(JSON.stringify({figures:3,directory:__dirname}));
})().catch(e=>{console.error(e);process.exit(1);});
