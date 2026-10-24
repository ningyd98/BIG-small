import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {importRuntimeModule} from '/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs';
const {FileBlob,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const dir=path.dirname(fileURLToPath(import.meta.url));
const input='/home/ningyd/.codex/attachments/9fe2531b-6c89-4fa8-b3ca-a3037f129e75/开题报告.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(input));
const original=[...p.slides.items];
const layouts=await Promise.all(original.map(s=>s.export({format:'layout'})));
const RED='#A60000',INK='#202020',MUTED='#666666',FONT='Noto Sans CJK SC';
const pos=(left,top,width,height)=>({left,top,width,height});
function edit(e,text,position,style={}){
 const s=p.resolve(e.id);s.text=text;
 s.text.style={...e.style,typeface:FONT,verticalAlignment:'middle',insets:0,...style};
 if(position)s.position=position;
 return s;
}
function find(n,query){return layouts[n-1].elements.find(e=>e.text?.startsWith(query));}
function change(n,query,text,position,style){const e=find(n,query);if(!e)throw Error(`Missing source ${n}: ${query}`);return edit(e,text,position,style);}
function title(n,text){const e=layouts[n-1].elements.find(e=>e.kind==='textbox'&&e.position.top===34);return edit(e,text,undefined,{fontSize:32});}
function add(slide,name,text,position,size=24,color=INK,bold=false){
 const s=slide.shapes.add({geometry:'textbox',name,position,fill:'none',line:{fill:'none',width:0}});
 s.text=text;s.text.style={typeface:FONT,fontSize:size,color,bold,alignment:'left',verticalAlignment:'middle',insets:0};return s;
}
function values(n,rows){
 const e=layouts[n-1].elements.find(e=>e.kind==='table'),t=p.resolve(e.id);
 for(let r=0;r<rows.length;r++)for(let c=0;c<rows[r].length;c++){
  t.cells.set(r,c,rows[r][c]);t.getCell(r,c).text.style={typeface:FONT,fontSize:r?26:26,color:r?INK:'#FFFFFF',bold:r===0};
 }
 return t;
}
function newTable(n,rows,box,widths,heights,size=25){
 const old=layouts[n-1].elements.find(e=>e.kind==='table');p.delete(old.id);
 const t=original[n-1].tables.add({rows:rows.length,columns:rows[0].length,...box,columnWidths:widths,values:rows});
 t.styleOptions={headerRow:true,bandedRows:false};
 t.borders.assign({style:'solid',fill:'#FFFFFF',width:2});
 for(let r=0;r<rows.length;r++){
  t.rows[r].height=heights[r];
  t.cells.block({row:r,column:0,rowCount:1,columnCount:rows[r].length}).assign({fill:r===0?RED:r%2?'#F2E8E9':'#FAF6F7',textStyle:{typeface:FONT,fontSize:size,color:r===0?'#FFFFFF':INK,bold:r===0},margins:{left:12,right:12,top:6,bottom:6},anchor:'center'});
 }
 return t;
}

// One duplicated own-template page supplies the reference's missing TOC role.
const toc=original[10].duplicate();
const tl=await toc.export({format:'layout'});
const te=q=>tl.elements.find(e=>e.text?.startsWith(q));
edit(te('10  预期成果'),'论文目录');
[['系统成果','1','形成自然语言','选题背景与意义',180],['方法成果','2','给出远程方案','研究内容与结构',340],['工程价值','3','量化任务质量','毕设进度安排',500]].forEach(([a,b,c,d,y])=>{
 edit(te(a),b,pos(155,y,100,65),{fontSize:40});edit(te(c),d,pos(280,y,830,65),{fontSize:38});
});
p.delete(te('范围限定').id);

// 1: Background, representative work, and the engineering-management value.
title(2,'1  选题背景与意义');
change(2,'复杂任务','背景',pos(75,135,550,45));
change(2,'理解自然语言','自然语言与多步任务增加计算需求\n小型设备受算力、功耗与成本约束\n本地执行仍需及时响应',pos(75,190,550,135),{fontSize:27});
change(2,'小型设备','研究现状',pos(75,345,550,45));
change(2,'算力、内存','SayCan：以技能可行性约束语言规划\nInner Monologue：以环境反馈修正规划\n仍需衔接方案有效性、介入时机\n与异常恢复边界',pos(75,400,550,150),{fontSize:25});
change(2,'核心问题','工程意义：权衡任务质量、响应时间与调用成本，\n为系统可靠性设计和资源预算提供依据。',pos(75,595,1135,65),{fontSize:27});
original[1].speakerNotes.text='研究背景及工程管理价值。场景图为概念示意，不是实验结果。\n[Sources]\nhttps://arxiv.org/abs/2204.01691 （SayCan，语言模型与技能可行性结合）\nhttps://arxiv.org/abs/2207.05608 （Inner Monologue，利用环境反馈进行闭环规划）\n[/Sources]';

title(3,'1  选题背景与意义');
values(3,[['关键痛点','典型表现','解决思路'],['方案有效性','云端结果返回时\n任务或环境已变化','返回时与提交前联合核验\n观测、任务版本和物理条件'],['协同调用成本','固定周期请求可能重复\n增加等待与远程调用','依据任务进展、风险与成本\n按事件选择处理路径'],['异常恢复代价','局部失败触发整段重做\n有效动作被重复执行','独立核验动作效果\n保留成果并在预算内恢复']]);
change(3,'研究重点','研究重点：方案可执行、调用有依据、异常有边界',undefined,{fontSize:28});

// 2.1: Retain the existing architecture artwork and make its proposed scope explicit.
title(4,'2.1  研究内容—系统基础与验证平台');
add(original[3],'研究内容','研究内容：构建云边端分层系统，在七关节 Franka-like 物理仿真中验证有限抓放任务',pos(75,112,1140,65),25);
p.resolve(layouts[3].elements.find(e=>e.kind==='image').id).position=pos(30,195,660,440);
change(4,'云端：','解决方案｜云端规划',pos(715,190,500,42),{fontSize:29});
change(4,'理解任务','Qwen3.8-Max 理解任务与分解步骤\n输出结构化方案，支持按需重规划',pos(715,237,500,75),{fontSize:25});
change(4,'边缘：','解决方案｜边缘协同',pos(715,330,500,42),{fontSize:29});
change(4,'管理状态','规则与成本策略管理状态、筛选动作\n核验方案有效性；模型选型后置',pos(715,377,500,75),{fontSize:25});
change(4,'端侧：','解决方案｜端侧执行',pos(715,470,500,42),{fontSize:29});
change(4,'感知定位','OpenCV RGB-D、可见标记与顶视相机\n现有控制器执行技能，保留独立安全保护',pos(715,517,500,80),{fontSize:25});
add(original[3],'已有基础与边界','已有基础：限定的软件链路检查已通过；物理闭环与正式实验尚未验收。\n图中恢复为拟研究能力；实机验证作为后续扩展。',pos(75,635,1040,55),21,MUTED);

title(5,'2.2  研究内容—观测与规划一致性检查');
change(5,'检查时机','研究内容：在方案返回时、动作提交前核验执行条件',undefined,{fontSize:30});
values(5,[['核验对象','解决方案：判断依据','失效后的处理'],['观测与目标','采集时间、目标身份\n深度与三维几何条件','重新观测，更新状态'],['任务与方案','任务版本、步骤前置条件\n实际执行进度','拒绝迟到或失效方案\n必要时请求重规划'],['动作提交','当前物理约束与安全条件','阻止执行或安全停止']]);
change(5,'信息','验证：注入失效情形，评价误放行与误拒。\n各对照组均保留基础版本、几何与安全检查；信息较新不等于动作可执行。',pos(75,615,1135,58),{fontSize:23});

title(6,'2.3  研究内容—事件驱动的云边协同决策');
change(6,'决策输入','研究内容：依据执行进度、风险、耗时与成本，选择本地处理或请求云端',pos(75,125,1135,65),{fontSize:27});
p.resolve(layouts[5].elements.find(e=>e.kind==='image').id).position=pos(280,185,720,360);
add(original[5],'能力边界','能力边界：局部恢复为拟研究分支，经验证后启用。',pos(75,528,1135,40),24,MUTED);
change(6,'按需触发','解决方案：能力与安全筛选 → 风险与成本比较 → 异步管理与请求去重',pos(75,575,1135,42),{fontSize:26});
add(original[5],'评价口径','评价：请求次数、传输字节、实际计费量分别统计；账单未知时保留未知。',pos(75,625,1135,40),24);

title(7,'2.4  研究内容—基于效果依赖的有限恢复');
add(original[6],'研究内容','研究内容：依据前置条件与动作效果确定失败范围，避免重复已完成操作',pos(75,110,1135,42),25);
change(7,'示例','示例：物体 A 已放置，物体 B 抓取滑落',pos(75,166,1135,45),{fontSize:29});
values(7,[['处置阶段','解决方案（拟实现）'],['识别失效环节','根据步骤前置条件与动作效果，定位失败影响范围'],['保留有效成果','独立复核 A 的放置效果，避免重复已完成操作'],['执行局部补偿','重新观测 B，组合抓取、搬运与放置技能'],['限制恢复预算','约束重试次数、总耗时与远程调用预算'],['升级或停止','无法恢复时请求重规划，必要时安全停止']]);
change(7,'动作控制','当前尚未启用；拟在预定义可恢复故障下，对比局部恢复与完整重规划。\n验证：控制返回成功后，仍需独立核验是否产生预期动作效果。',pos(75,612,1135,60),{fontSize:23});

// 2.5: Merge the original target and experimental-design pages without implying results.
title(9,'2.5  研究内容—对照实验与工程评价');
change(9,'实验范围','预期目标（待正式实验验证）',pos(75,128,1120,42),{fontSize:29});
change(9,'物理仿真','定位误差 P90 ≤ 10 mm（同时报告有效观测覆盖率）；静态抓放成功率 ≥ 90%\n相对合格固定周期基线，远程请求均值降低 ≥ 30%',pos(75,181,1135,75),{fontSize:25});
newTable(9,[['实验设计','解决方案与评价内容'],['主对照','纯本地、固定周期、固定阈值与本课题方法；任务配对、共用安全层'],['三模块消融','分别移除一致性增强、协同决策或恢复模块，考察独立作用'],['工程度量','任务成功、失败惩罚耗时、请求数、传输字节与实际计费量']],{left:70,top:278,width:1140,height:244},[240,900],[49,65,65,65],24);
change(9,'变化条件','质量约束：成功率差的单侧 95% 置信下界 > −3 个百分点；\n安全事件率差的单侧 95% 置信上界 ≤ +1 个百分点。',pos(75,539,1135,70),{fontSize:24});
add(original[8],'实验口径','所有失败与停止保留在预定分母；正式样本量由独立功效试验确定。\n离线真值仅用于评价；与静态单步目标分开报告多步扰动任务。',pos(75,614,1135,58),22,MUTED);

// 2.6: The reference's two-page thesis outline, using own red-table/group style.
title(8,'2.6  论文基本架构（1/2）');
newTable(8,[['拟定章节','主要内容'],['第一章  绪论','1.1 研究背景与工程意义\n1.2 国内外研究现状\n1.3 研究内容与论文组织'],['第二章  相关技术与系统总体设计','2.1 云边协同与机器人执行基础\n2.2 需求分析与系统约束\n2.3 分层架构与接口设计'],['第三章  一致性检查与协同决策方法','3.1 状态与方案有效性核验\n3.2 动作能力与安全筛选\n3.3 事件触发及风险、成本决策'],['第四章  有限恢复与系统实现','4.1 前置条件与效果依赖\n4.2 局部补偿与恢复预算\n4.3 系统实现与集成']],{left:70,top:145,width:1140,height:480},[550,590],[48,108,108,108,108],25);
change(8,'以上','论述顺序：工程问题 → 系统设计 → 关键方法 → 系统实现',pos(75,638,1135,35),{fontSize:24});

title(11,'2.6  论文基本架构（2/2）');
change(11,'系统成果','第五章\n实验设计与工程评价',pos(75,150,280,110),{fontSize:28});
change(11,'形成自然语言','5.1 任务集、配对基线与评价口径\n5.2 一致性、决策、恢复三模块消融\n5.3 成功率、延迟、调用成本与可靠性分析',pos(380,150,825,120),{fontSize:27});
change(11,'方法成果','第六章\n总结与展望',pos(75,325,280,110),{fontSize:28});
change(11,'给出远程方案','6.1 研究结论与适用边界\n6.2 研究不足\n6.3 实机验证与后续扩展',pos(380,325,825,120),{fontSize:27});
change(11,'工程价值','预期成果',pos(75,520,280,50),{fontSize:28});
change(11,'量化任务质量','受控仿真原型、系统与接口设计文档\n可复核实验资料、工程评价结论及学位论文',pos(380,505,825,95),{fontSize:27});
change(11,'范围限定','研究范围：受控仿真、已知刚性物体与有限步骤任务；实机验证作为后续扩展',pos(75,635,1135,35),{fontSize:22});

title(10,'3.1  时间进度安排');
const schedule=values(10,[['阶段','时间','计划与阶段产出'],['基础能力与基线','2026.10—11','完成阶段收尾与感知闭环；\n建立合格固定周期基线并冻结初始设置'],['方法实现与集成','2026.12—2027.01','实现一致性、事件决策与有限恢复；\n完成方法冻结及独立功效试验'],['实验与分析','2027.02—03','开展正式对照与消融实验；\n完成统计分析与论文初稿'],['论文与答辩','2027.04—05','补充验证、修改定稿与送审；\n按学院安排准备答辩']]);
for(let r=1;r<5;r++)schedule.getCell(r,2).text.style={typeface:FONT,fontSize:24,color:INK};
change(10,'主要交付物','各阶段以前置能力和验证通过为条件；前置未满足则顺延。\n预期交付：仿真原型、设计文档、可复核实验资料、学位论文。',pos(75,613,1135,60),{fontSize:24});

const order=[original[0],toc,original[1],original[2],original[3],original[4],original[5],original[6],original[8],original[7],original[10],original[9],original[11]];
for(let i=0;i<order.length;i++)order[i].moveTo(i);
for(let i=0;i<p.slides.items.length;i++){
 const slide=p.slides.items[i],l=await slide.export({format:'layout'});
 const folio=l.elements.find(e=>e.kind==='textbox'&&/^\d+ \/ 12$/.test(e.text||''));
 if(folio)edit(folio,`${i+1} / 13`);
 if(i!==2)slide.speakerNotes.text='';
 await fs.writeFile(path.join(dir,'evidence',`draft-slide-${i+1}-layout.json`),JSON.stringify(await slide.export({format:'layout'}),null,2));
}
await fs.mkdir(path.join(dir,'draft-render'),{recursive:true});
const pptx=await PresentationFile.exportPptx(p);await pptx.save(path.join(dir,'rewritten-draft.pptx'));
const finalImport=await PresentationFile.importPptx(await FileBlob.load(path.join(dir,'rewritten-draft.pptx')));
for(let i=0;i<finalImport.slides.items.length;i++){
 const blob=await finalImport.export({slide:finalImport.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(dir,'draft-render',`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
console.log(JSON.stringify({status:'authored_exported_and_rendered',slides:finalImport.slides.items.length,draft:path.join(dir,'rewritten-draft.pptx')}));
