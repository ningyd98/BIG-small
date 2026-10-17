from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from copy import deepcopy
import hashlib,json,sys

TMP=Path('/tmp/bigsmall-opening-application-20261011')
REF=TMP/'开题报告-2101210559丁亚伟.docx'
OUT=Path('/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261024-opening-application/开题申请表_集成电路工程_20261024.docx')
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W='{'+NS['w']+'}'
with ZipFile(REF) as z: parts={n:z.read(n) for n in z.namelist()}
root=E.fromstring(parts['word/document.xml']);body=root.find('w:body',NS)
source=deepcopy(body[19]);sect=deepcopy(body[-1]);school=deepcopy(body[16]);title=deepcopy(body[17])
rows=source.findall('w:tr',NS)
base=deepcopy(rows[5].findall('w:tc',NS)[1].findall('w:p',NS)[1])


def ensure(parent,name):
 e=parent.find('w:'+name,NS)
 if e is None:e=E.SubElement(parent,W+name)
 return e

def prop(parent,name,**kwargs):
 e=ensure(parent,name)
 for k,v in kwargs.items():e.set(W+k,str(v))
 return e

def paragraph(text,bold=False,indent=True,align='both',size=21,space=50):
 p=deepcopy(base)
 for ch in list(p):
  if ch.tag!=W+'pPr':p.remove(ch)
 pr=ensure(p,'pPr')
 for name in ['numPr','sectPr','pageBreakBefore','rPr']:
  e=pr.find('w:'+name,NS)
  if e is not None:pr.remove(e)
 prop(pr,'pStyle',val='Normal');prop(pr,'jc',val=align)
 prop(pr,'ind',firstLine=420 if indent else 0,start=0,end=0)
 prop(pr,'spacing',before=0,after=space,line=320,lineRule='exact')
 prop(pr,'snapToGrid',val='0');prop(pr,'widowControl',val='1')
 prop(pr,'keepNext',val='1' if bold else '0')
 r=E.SubElement(p,W+'r');rp=E.SubElement(r,W+'rPr')
 prop(rp,'rFonts',ascii='Times New Roman',hAnsi='Times New Roman',eastAsia='宋体',cs='Times New Roman')
 prop(rp,'color',val='000000');prop(rp,'sz',val=size);prop(rp,'szCs',val=size)
 if bold:prop(rp,'b')
 t=E.SubElement(r,W+'t');t.text=text
 if text.startswith(' ') or text.endswith(' '):t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
 return p

def fill(cell,blocks):
 for child in list(cell):
  if child.tag!=W+'tcPr':cell.remove(child)
 for x in blocks:
  if isinstance(x,str):cell.append(paragraph(x))
  else:cell.append(paragraph(x[1],bold=x[0]=='h',indent=x[0]=='p',align='left' if x[0] in ['h','ref','line'] else 'both'))

for x in list(body):body.remove(x)
fill(school,[('line','学校及学院：________________________________')]) if False else None
school=paragraph('学校及学院：________________________________',indent=False,align='center',size=21,space=120)
title=paragraph('论文开题报告申请表',bold=True,indent=False,align='center',size=30,space=200)
prop(title.find('w:pPr',NS),'pStyle',val='Title')
body.append(school);body.append(title)
# Retain the reference table, grids and border system. All values are task-specific.
metadata=[
 ['学生姓名','', '论文名称','面向边缘智能场景的小型机械臂云边协同控制系统的设计'],
 ['论文类型','工程类（√）／研究类（ ）','专业学位领域','集成电路工程'],
 ['申请开题日期','2026年10月24日','企业合作导师',''],
 ['', '', '学院指导教师',''],
 ['学号','', '研究方向','嵌入式智能系统与云边端协同控制'],
]
for i,vals in enumerate(metadata):
 for c,txt in zip(rows[i].findall('w:tc',NS),vals):
  fill(c,[('line',txt)])
  for p in c.findall('w:p',NS):
   prop(p.find('w:pPr',NS),'jc',val='center');prop(p.find('w:pPr',NS),'spacing',before=0,after=0,line=280,lineRule='exact')
  prop(ensure(c,'tcPr'),'vAlign',val='center')
# Compact the source header rows by replacing content, never reducing font size.
for row in rows[:5]:
 prop(ensure(row,'trPr'),'cantSplit')
# Replace legacy technical text and source figure slots in place.
background=[
 ('h','一、选题意义'),
 '本课题针对小型机械臂边缘计算资源有限、云端响应存在延迟以及视觉信息可能失效的问题，研究云端规划、边缘决策与端侧感知执行相结合的控制系统。通过在任务成功率和安全约束下优化计算与通信分工，为面向嵌入式处理器的智能控制系统设计、接口组织和资源利用提供工程依据。',
 ('h','国内外研究现状与立项依据'),
 '云机器人通过远程计算和共享资源扩展机器人能力，边缘计算则将部分处理任务部署在靠近传感器与执行器的位置，以改善响应时间和带宽利用[1-2]。已有机器人网络卸载研究将感知不确定性和通信成本纳入决策[3]；语言模型机器人研究通过技能可行性约束，将高层语义规划连接到物理执行[4]。这些工作为本课题的分层方案提供了基础。',
 '对实际操作任务而言，云端返回的方案可能依赖过期观测，端侧感知也可能受到遮挡和无效深度影响。因此，本课题重点研究“当前证据能否支持动作执行”以及“证据失效后如何有限修复”，在已有云边协同框架上建立从观测、判断、动作到效果验证的闭环。',
 '本课题依托BIGsmall项目，专业关联重点为嵌入式计算任务划分、传感与控制接口、通信资源约束及系统可靠性验证。近期以物理仿真和模拟云边端部署为主要验证环境，板级部署与真实机械臂验证另按设备条件开展，相关结论限定于实际验证范围。',
 ('h','主要参考文献'),
 ('ref','[1] Kehoe B, et al. A Survey of Research on Cloud Robotics and Automation. IEEE TASE, 2015, 12(2): 398–409.'),
 ('ref','[2] Shi W, et al. Edge Computing: Vision and Challenges. IEEE Internet of Things Journal, 2016, 3(5): 637–646.'),
 ('ref','[3] Chinchali S, et al. Network Offloading Policies for Cloud Robotics: A Learning-Based Approach. Robotics: Science and Systems, 2019.'),
 ('ref','[4] Ahn M, et al. Do As I Can, Not As I Say: Grounding Language in Robotic Affordances. Conference on Robot Learning, 2022.'),
]
research=[
 ('h','二、研究内容'),
 ('h','1. 已完成的工作'),
 '已建立任务契约、周期云端监督、事件触发边缘自治、模式选择、技能执行和安全检查等软件模块，并形成MuJoCo仿真运行、可视化工作台及实验记录工具。云端历史记录包括35次真实Max请求及响应有效性核验；端侧已实现OpenCV身份检查、RGB-D几何条件和三值判断，一次限定开发轨迹的4,807帧均完成原始读出及标记观测核验。',
 '当前资产已实际采集100组开发数据，运行来源和时效窗口软件已完成部分限定验收。上述工作证明了软件和局部仿真链路具备研究基础，尚不能替代完整动作资格或正式方法验证；旧版120组先导仅5组成功的负结果继续保留，后续需先建立合格基础闭环。',
 ('h','2. 研究方案与技术路线'),
 '云端沿用项目既定的Qwen3.8-Max方案，负责初始任务规划、监督与重规划；边缘侧汇总观测和执行状态，近期采用规则与实测成本进行受约束判断，边缘模型选型后置；端侧采用OpenCV、RGB-D几何及已选可见姿态标记，保留顶视相机、现有控制器、技能执行器与SafetyShield。',
 ('line','技术路线：任务输入 → 云端规划 → 边缘证据与能力检查 → 端侧受控执行 → 新观测与效果验证 → 继续、重观测、修复、请求云端或停止。'),
 '拟解决三个关键问题：一是将目标身份、观测时刻、标定版本和几何误差界与动作绑定，在云端返回及动作提交前复核；二是在满足能力与风险约束的候选中，联合考虑计算、通信和任务代价；三是根据证据依赖定位受影响的未完成步骤，在有限预算内局部修复，并保护已经确认完成的物理效果。',
 '模型请求异步执行，普通决策在技能边界应用，硬停止独立于模型响应。研究中记录实际计算平台、CPU/GPU占用、内存、收发字节和端到端延迟，评价软硬件接口组织及资源分配对系统性能的影响。',
 ('h','3. 研究目标与验证方法'),
 '采用相同场景、模型、控制器及安全约束，对比周期监督、固定阈值事件触发、规则模式选择和拟研究方法；先在0.5、1、2、5秒周期上筛选合格基线，再开展相互隔离的基础先导、方法冻结、功效先导和正式实验。正式样本量按预定功效规则从每方法600、1,200、1,800、2,400个配对场景组中选择。',
 '计划目标包括：有效定位误差P90不超过10 mm，独立静态抓放成功率不低于90%；相对合格周期基线，云请求均值降低至少30%，同时满足成功率差单侧95%下界大于−3个百分点、安全违规率差单侧95%上界不超过+1个百分点；在预定义200个可恢复故障组中，恢复成功率不低于80%。以上均为待验证目标。',
 '在线效果验证与独立物理评价共同判定任务成功。训练、标定、选择与测试按来源组隔离；原始失败、超时、停止和阻塞均保留。现有软件、数据和仿真平台可支持方法开发，近期重点是补齐几何、时效与执行边界，再进入正式对照。',
 ('h','三、论文架构'),
 ('line','第一章 绪论：研究背景、国内外现状、研究问题与主要内容。'),
 ('line','第二章 系统需求与总体设计：任务约束、计算平台、云边端分工、传感与控制接口、资源预算。'),
 ('line','第三章 端侧视觉与证据约束：RGB-D采集、身份与姿态观测、几何误差、有效期及效果验证。'),
 ('line','第四章 云边协同决策：任务契约、周期与事件机制、风险校准、成本决策及模式切换。'),
 ('line','第五章 局部修复与系统实现：失败依赖、恢复预算、完成效果保护、控制器集成与状态持久化。'),
 ('line','第六章 实验与性能分析：基线筛选、正式比较、消融与恢复、资源开销、失败分析及复现。'),
 ('line','第七章 总结与展望：研究结论、工程价值、局限与后续板级及实机验证。'),
 ('h','四、成果展示'),
 '已申请发明专利1项：《机器人控制方法、装备及存储介质》，申请号202611505816.9。相关技术涉及云端计划有效性验证、边缘安全决策及执行模式协调，与论文的系统接口、协同决策和可靠执行内容相对应。',
 '现有工程成果包括系统软件原型、仿真工作台、局部开发验证记录和研究文稿；后续拟形成学位论文、正式对照与消融结果、资源开销分析以及可追溯的演示和复现材料。学术论文发表或录用信息尚未登记。',
 '本课题与“集成电路工程”的关联拟落实到面向嵌入式处理器的系统设计、传感控制接口和资源约束评价。现有专利处于申请阶段，是否满足毕业成果要求，须结合学院适用规定、发明人排序和成果证明材料核定，不能仅依据申请号认定达标。',
]
schedule=[
 ('h','五、进度安排'),
 ('line','2026年10月12—23日：完成开题材料与专利证明整理，核对专业要求；继续完善端侧证据、运行来源和时效检查。'),
 ('line','2026年10月24日：提交开题申请，按学院安排参加评审，并根据意见完善研究范围。'),
 ('line','2026年10月25日—11月1日：贯通当前配置的基础闭环，补齐几何和运动证据，筛选周期基线，开展新120组基础先导；达标后冻结初始协议。'),
 ('line','2026年11月2—15日：完成独立风险校准、证据有效期及提交前复核，验证遮挡、旧帧、版本冲突和迟到返回等情况。'),
 ('line','2026年11月16—29日：完善协同决策与局部修复，验证预算控制、模式交接及重复执行防护，建立公平比较条件。'),
 ('line','2026年11月30日—12月6日：冻结方法及配置，运行另120组功效先导，核定正式样本量与资源预算。'),
 ('line','2026年12月7—20日：开展正式比较、恢复与消融实验，完成统计、资源开销和失败分析，形成论文初稿。'),
 ('line','2026年12月21—27日：根据导师意见修改论文，整理专利、演示和复现材料；后续评阅与答辩按学院正式日程执行。'),
 '各日期为研究计划目标，执行以依赖和验收条件为准。若基础能力或预算未就绪，则与导师协商顺延，不降低实验门槛。12月27日为文稿与材料交付目标，并非已经确认的答辩日期。',
]
for i,blocks in [(5,background),(6,research),(7,schedule)]:
 cell=rows[i].findall('w:tc',NS)[1];fill(cell,blocks)
 # Small top/bottom padding and normal source width, no fixed heights.
 cp=ensure(cell,'tcPr');mar=ensure(cp,'tcMar')
 prop(mar,'top',w=60,type='dxa');prop(mar,'bottom',w=60,type='dxa')
 label=rows[i].findall('w:tc',NS)[0]
 labeltext=['技术背景','研究开发方案','进展计划'][i-5]
 fill(label,[('line',labeltext)])
 prop(label.find('w:p/w:pPr',NS),'jc',val='center')
# Only the application is requested; cover and blank review sheet are out of scope.
body.append(source)
body.append(paragraph('',indent=False,space=0))
body.append(sect)
parts['word/document.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
styles=E.fromstring(parts['word/styles.xml'])
if not styles.xpath('./w:style[@w:styleId="Title"]',namespaces=NS):
 st=E.SubElement(styles,W+'style');st.set(W+'type','paragraph');st.set(W+'styleId','Title')
 prop(st,'name',val='Title');prop(st,'basedOn',val='Normal');prop(st,'qFormat')
 sp=E.SubElement(st,W+'pPr');prop(sp,'jc',val='center');prop(sp,'keepNext')
 rp=E.SubElement(st,W+'rPr');prop(rp,'b');prop(rp,'color',val='000000');prop(rp,'sz',val=30)
parts['word/styles.xml']=E.tostring(styles,xml_declaration=True,encoding='UTF-8',standalone=True)
core=E.fromstring(parts['docProps/core.xml'])
for ch in list(core):
 if E.QName(ch).localname in ['creator','lastModifiedBy','title','subject','description','keywords']:core.remove(ch)
x=E.SubElement(core,'{http://purl.org/dc/elements/1.1/}title');x.text='论文开题报告申请表'
parts['docProps/core.xml']=E.tostring(core,xml_declaration=True,encoding='UTF-8',standalone=True)
OUT.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
 for n,data in parts.items():z.writestr(n,data)
text='\n'.join(root.xpath('//w:t/text()',namespaces=NS));(TMP/'application-text.txt').write_text(text)
print(json.dumps({'output':str(OUT),'characters':len(text),'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest()},ensure_ascii=False))
