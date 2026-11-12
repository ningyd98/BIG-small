# R613 真实采集共享路径耗时诊断

在R610已交付的0446a354当前来源上，按实际Astra计划执行一次EGL采集诊断。使用普通MuJoCoPhysicsBackend、借用的MuJoCoCaptureSession和公开VisualRawRecorderV3，未绑定worker/source，不调用NativeFullHorizonRecorder私有工厂。425份应用Python源码加1份场景资产、1451份运行时/解释器文件、23份当前GL库和2份本地助手在运行前后校验一致；场景是无外部XML/mesh依赖的原侧Y75mm版本，320×240、seed613001、原0.001深度噪声。

实际计数闭合：initialize、XML模型、MjData、reset/mj_resetData/mj_forward、相机和Renderer各1次；3次CAPTURE均BEGIN/END完整，8次render为RGB3/深度3/实例2。reset原自动帧无实例图，instances文件为空；两次显式帧各76800个实例ID，未补造缺失数据。原路径完成5次观测转换、8次新PNG打开/verify，退出只自动flush一次。没有物理步、CONTROL/COMMAND、IK、执行器动作、教师、ArUco或模型/云端/硬件运行。

墙钟分别为initialize1.796ms、reset149.654ms、普通显式采集65.739ms、带cProfile的显式采集183.497ms、三帧自动flush176.281ms。普通采集CPU65.742ms，带profile183.499ms，flush176.271ms。每种显式模式样本量仅1；profile有明显工具开销，不能把183ms当作未剖析性能，也不能据此给出稳态/分位数或速度提升。

剖析总exclusive self约182.963ms。按互不重叠文件self汇总，observations.py63.329ms、backend.py41.065ms、camera.py26.971ms、dataclasses.py21.292ms；可定位下一步检查逐像素浮点解包、掩码生成、标量tuple构造及不可变审计拷贝。cumulative含子调用/递归重叠，仅作路径说明，不与self相加。renderer.py自身self不等于GPU总渲染耗时，本轮不是GPU设备计时，也不能把全部历史耗时归给某一模块。

父进程1.717s内回收子进程，exit0、无存活进程组；子进程自身总1.579s，最大RSS311521280字节，newrun共26文件/3500029字节，低于180s/2GiB/64MiB上限。GPU锁inode/大小/mtime未变；observer/audit/拒绝/主次错误均为空，stderr为空，backend及Renderer已关闭。原件先冻结，再仅解析profile和JSON/hash，26文件成员/字节/SHA/mtime均未变；没有额外图像解码或再次实际运行。

普通recorder按设计为SOURCE_CONSISTENCY_ONLY、UNBOUND、INCOMPLETE，原因列表为空，不能写成完整动作来源。此探针包含真实采集、边界拷贝、两次显式返回编码及延迟flush，但不复现R595的NativeFullHorizon spool、应用/lease/DB/Shield和连续每步采集。不能以65.7ms乘历史3389帧归因624秒，也不能把它称为8秒准入验证或R608的native提速证明。

本轮未改产品源码、未运行新pytest/lint，R610软件结论及其退出清理限制保持。历史教师尝试仍3次，R595准入0/8、合格0/9，native UNKNOWN/authority UNAVAILABLE，正式未验收。下一步需另行实际Astra计划做有证据的CPU路径优化；新来源实际比较须另开一次额度，不能重跑本探针或复用v5。

只交付本步骤、阶段与JSON三份派生报告；全帧/实例/depth/模型输出、profile、助手、源/运行时清单、数据库与凭据均不作为公开复现包。
