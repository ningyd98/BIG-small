const fs = require('fs');
const path = require('path');
const {createRequire}=require('module');
const bundleRequire=createRequire('/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp/package.json');
const sharp=bundleRequire('sharp');
const mathRequire=createRequire(path.resolve(__dirname,'math-runtime/package.json'));
const {mathjax}=mathRequire('mathjax-full/js/mathjax.js');
const {TeX}=mathRequire('mathjax-full/js/input/tex.js');
const {SVG}=mathRequire('mathjax-full/js/output/svg.js');
const {liteAdaptor}=mathRequire('mathjax-full/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler}=mathRequire('mathjax-full/js/handlers/html.js');
const {AllPackages}=mathRequire('mathjax-full/js/input/tex/AllPackages.js');
const base=path.resolve(__dirname,'..');
const adaptor=liteAdaptor();RegisterHTMLHandler(adaptor);
const mj=mathjax.document('',{InputJax:new TeX({packages:AllPackages}),OutputJax:new SVG({fontCache:'local'})});
const src=fs.readFileSync(path.join(base,'开题报告.md'),'utf8');
const eqs=[...src.matchAll(/^:::equation (.*)$/mg)].map(m=>m[1]);
async function equation(tex,i){
 let markup=adaptor.outerHTML(mj.convert(tex,{display:true}));let svg=markup.match(/<svg[\s\S]*<\/svg>/)[0];
 if(!svg.includes('xmlns='))svg=svg.replace('<svg ','<svg xmlns="http://www.w3.org/2000/svg" ');
 let w=0,h=0;svg=svg.replace(/(width|height)="([\d.]+)ex"/g,(_,a,b)=>{let n=Number(b)*8.5;if(a==='width')w=n;else h=n;return `${a}="${n}px"`;});
 svg=svg.replace(/currentColor/g,'#000000');let stem=`equation-${i+1}`;fs.writeFileSync(path.join(__dirname,stem+'.svg'),svg);
 await sharp(Buffer.from(svg),{density:400}).png().toFile(path.join(__dirname,stem+'.png'));
 return {index:i+1,latex:tex,width_px:w,height_px:h,path:stem+'.png'};
}
function frame(h){return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${h}" viewBox="0 0 1200 ${h}"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#303030"/></marker></defs><rect width="1200" height="${h}" fill="white"/><g font-family="Noto Sans CJK SC, sans-serif" fill="#111111">`;}
function text(x,y,lines,size=28){return `<text x="${x}" y="${y}" text-anchor="middle" font-size="${size}">${lines.map((l,i)=>`<tspan x="${x}" dy="${i===0?0:size+9}">${l}</tspan>`).join('')}</text>`;}
function box(x,y,w,h,lines,size=28){let ty=y+h/2-((lines.length-1)*(size+9))/2+size*0.32;return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="#f6f6f6" stroke="#666" stroke-width="2"/>${text(x+w/2,ty,lines,size)}`;}
function line(x1,y1,x2,y2,dash=false){return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#303030" stroke-width="2.6" ${dash?'stroke-dasharray="8 6"':''} marker-end="url(#arrow)"/>`;}
function poly(points,dash=false){return `<polyline points="${points}" fill="none" stroke="#303030" stroke-width="2.6" ${dash?'stroke-dasharray="8 6"':''} marker-end="url(#arrow)"/>`;}
async function figure(name,svg){fs.writeFileSync(path.join(__dirname,name+'.svg'),svg);await sharp(Buffer.from(svg)).resize({width:2400}).png().toFile(path.join(__dirname,name+'.png'));}
(async()=>{
 const meta=[];for(let i=0;i<eqs.length;i++)meta.push(await equation(eqs[i],i));fs.writeFileSync(path.join(__dirname,'equations.json'),JSON.stringify(meta,null,2));
 let a=frame(630)+text(600,40,['云端慢循环：监督机会与复杂推理分别调度'],30)+box(90,70,410,85,['任务理解 / 按需重规划'])+box(700,70,410,85,['轻量周期监督 / 事件响应'])+line(295,155,510,208)+line(905,155,690,208)+box(390,215,420,90,['计划封装体 / TaskContract'])+poly('600,305 600,327 119,327 119,382')+text(600,360,['边缘快循环：验证、筛选与执行持续运行'],29);
 let nodes=[['契约与上下文','有效性验证'],['独立','SafetyShield'],['任务 / 技能','执行器'],['RobotAdapter','统一动作语义'],['模拟设备','物理与传感器']];
 for(let i=0;i<nodes.length;i++){a+=box(10+i*242,390,218,94,nodes[i],25);if(i<4)a+=line(228+i*242,437,245+i*242,437);}
 a+=box(390,532,420,75,['状态反馈 / 事件 / 有界恢复'],27)+poly('1100,484 1100,570 818,570')+poly('382,570 4,570 4,113 80,113',true)+text(160,540,['异步反馈'],22)+'</g></svg>';await figure('architecture',a);
 let h=frame(740)+box(70,20,230,60,['云端系统'])+box(485,20,230,60,['边缘协同 / 安全层'],25)+box(900,20,230,60,['模拟设备']);
 h+=line(185,85,185,690,true)+line(600,85,600,690,true)+line(1015,85,1015,690,true);
 h+=line(185,135,590,135)+text(385,118,['新计划到达：候选资格'],24)+box(425,167,350,75,['第一次校验 / 准备连接段'],25);
 h+=line(610,280,1005,280)+text(810,262,['旧计划保持唯一执行权'],24)+box(425,316,350,80,['等待可行交接窗口','候选尚未获得执行权'],25);
 h+=line(1015,435,610,435)+text(810,417,['读取最新状态与传感器'],24)+box(425,465,350,85,['第二次验证 + 代次检查','新计划与连接段均需通过'],24);
 h+=line(610,588,1005,588)+text(810,570,['通过：原子提交并开始新段'],24)+line(590,625,195,625)+text(385,610,['提交 ACK / 失效原因'],24)+text(600,715,['复核失败：旧段重新验证；否则保持或停止'],25)+'</g></svg>';await figure('handover',h);
 let e=frame(530)+text(600,38,['研究协议先冻结，再运行与验证'],30);
 let row1=[['冻结任务与假设','阈值 / 终态 / 统计'],['共同初值与参数','控制 / 时间 / 观测'],['配对重复运行','MuJoCo 与 Isaac']];
 for(let i=0;i<3;i++){e+=box(30+i*400,80,340,105,row1[i],27);if(i<2)e+=line(370+i*400,132,422+i*400,132);}
 e+=line(1000,185,1000,263);let row2=[['效果量与适用范围','方法支持或反例'],['完整事件与原始轨迹','配对 / 溯源 / 终态'],['资格与真实性验证','参数实际生效']];
 for(let i=0;i<3;i++){e+=box(30+i*400,280,340,105,row2[i],27);if(i>0)e+=line(22+i*400,332,378+(i-1)*400,332);}
 e+=box(680,435,460,65,['未通过记录保留并注明原因'],25)+line(1000,385,1000,428)+text(315,474,['确认分析与探索分析分开'],27)+'</g></svg>';await figure('experiment',e);
 console.log(JSON.stringify({equations:eqs.length,figures:3}));
})().catch(e=>{console.error(e);process.exit(1);});
