import fs from 'node:fs';
import path from 'node:path';
import sharp from '/home/ningyd/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp/lib/index.js';

const out='/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application';
const elements=[];
const xml=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const rect=(x,y,w,h,fill='#fff',stroke='#333',sw=2)=>elements.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`);
const text=(x,y,s,size=30,anchor='middle',weight=400)=>elements.push(`<text x="${x}" y="${y}" text-anchor="${anchor}" font-size="${size}" font-weight="${weight}">${xml(s)}</text>`);
const arrow=(points)=>elements.push(`<polyline points="${points.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#333" stroke-width="2.8" marker-end="url(#arrow)"/>`);
const box=(x,y,w,h,title,lines=[])=>{rect(x,y,w,h);text(x+w/2,y+39,title,31,'middle',600);lines.forEach((s,i)=>text(x+w/2,y+78+i*34,s,28));};

text(700,45,'小型机械臂云边协同控制系统架构',38,'middle',600);
rect(490,77,420,64,'#fff');text(700,120,'任务指令',32,'middle',600);
arrow([[700,141],[700,180]]);

rect(40,180,1320,220,'#f7f8f9');
text(75,226,'云端  Qwen3.8-Max',33,'start',600);
box(90,260,340,110,'任务与场景理解',['目标与任务语义']);
box(530,260,340,110,'任务规划与监督',['步骤与执行条件']);
box(970,260,340,110,'异常分析与重规划',['更新受影响的方案']);
arrow([[430,315],[520,315]]);arrow([[970,315],[880,315]]);

arrow([[390,400],[390,535]]);
text(418,460,'结构化步骤 / 条件',28,'start');
arrow([[1000,540],[1000,405]]);
text(1028,455,'异步云端请求',28,'start');
text(1028,492,'任务状态与场景',28,'start');

rect(40,540,1320,350,'#f7f8f9');
text(75,586,'边缘侧  状态管理与协同决策',33,'start',600);
text(1325,624,'规则与成本判断；边缘模型后续选型',25,'end');
box(90,655,340,134,'任务状态管理',['观测与动作反馈','步骤及版本信息']);
box(530,655,340,134,'执行条件检查',['身份 / 时效 / 几何','候选能力与风险约束']);
box(970,655,340,134,'事件触发与选择',['风险 / 时间 / 通信成本','局部修复与请求调度']);
arrow([[430,721],[520,721]]);arrow([[870,721],[960,721]]);
text(700,852,'继续执行    重新观测    局部修复    请求云端    停止',28,'middle',500);

arrow([[310,1000],[310,895]]);
text(335,957,'新观测 / 效果反馈',28,'start');
arrow([[1050,890],[1050,995]]);
text(1078,937,'技能指令',28,'start');
text(1078,975,'重观测 / 停止',28,'start');

rect(40,1000,1320,420,'#f7f8f9');
text(75,1046,'端侧  视觉感知与动作执行',33,'start',600);
box(90,1085,520,98,'顶视 RGB-D 相机',['可见姿态标记与场景图像']);
box(790,1085,520,98,'动作约束检查与独立停止',['SafetyShield']);
box(90,1230,520,100,'OpenCV 与 RGB-D 几何',['身份 / 几何 / 时序 / 效果证据']);
box(790,1230,520,100,'技能执行与现有控制器',['抓取 / 搬运 / 放置']);
arrow([[350,1183],[350,1225]]);
arrow([[1050,1183],[1050,1225]]);
arrow([[1050,1330],[1050,1360],[350,1360],[350,1335]]);
text(700,1400,'新图像 / 本体反馈 / 执行结果',27);

text(700,1470,'验证环境：MuJoCo 物理仿真；真实设备实验按设备条件安排',27);
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1510" viewBox="0 0 1400 1510"><title>小型机械臂云边协同控制系统架构</title><desc>云端Qwen3.8-Max承担任务规划、监督和重规划；边缘侧维护状态、检查条件并以事件与成本进行协同决策；端侧通过顶视RGB-D相机、可见姿态标记和OpenCV获取证据，经过SafetyShield交由技能执行器和控制器完成动作，新观测及反馈返回边缘侧形成闭环。云端请求异步，边缘模型选型后置。</desc><defs><marker id="arrow" markerWidth="10" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,4.5 L0,9 Z" fill="#333"/></marker></defs><rect width="1400" height="1510" fill="white"/><g fill="#111" font-family="Noto Sans CJK SC, sans-serif">${elements.join('')}</g></svg>`;
fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,'系统架构图_云边端.svg'),svg);
await sharp(Buffer.from(svg),{density:192}).png().toFile(path.join(out,'系统架构图_云边端.png'));
console.log(JSON.stringify({svg:path.join(out,'系统架构图_云边端.svg'),png:path.join(out,'系统架构图_云边端.png'),size:await sharp(path.join(out,'系统架构图_云边端.png')).metadata()}));
