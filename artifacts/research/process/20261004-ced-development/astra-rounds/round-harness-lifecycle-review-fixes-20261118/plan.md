# Astra：H1与Phase12审查七项修复

实际`gpt-6-astra`，2026-11-18，PLANNED_NOT_FIXED。独立review的5 Important/2 Minor已由root核实；本计划绑定review及18项因果输入SHA（含现有新测试、R545原件、旧18行来源）。先增加对应RED，再实施GREEN，不追认已有证据为修复结果。

**H1代理范围**：仅harness的CLI/config/evidence/checkout、必要私有native bootstrap、对应测试/说明。①同一native子进程先复用原R545 configure_overlay的解释器、baseline.pth、版本/来源/哈希、CPUABI和零CUDA校验，再核实选定checkout的实际项目模块路径/SHA，最后delegate原入口；原R545不改，find_spec存在不再作准入。正确molmoer/错误groundingpi各CPU --help验证，错误环境须在创建episode前失败。②区分预检未启动和已spawn未知：缺manifest/信号/写盘不完整保留真实raw exit、signal、wrapper code及已有阶段文件，INCOMPLETE_UNKNOWN、成本未知/null；仅确实未进episode才NOT_STARTED。③prepare保持零活动，明确planned配置/hash与原scene-assignment的effective字段，列出未应用的scene_split/servo/camera；不把development seed的计划布局称已准备。④证据必须有合法阶段/status/mode及阶段必需字段/类型；schema-only拒绝，PREPARED且来源COMPLETE需绑定scene-assignment/source-hashes。真实FAILED/INTERRUPTED按完整/部分证据如实表达，未知不补零、不KeyError。⑤visual_servo先严格bool判定，拒JSON1/1.0而保持true指纹。

**root Phase12范围**：仅run_phase12_runtime_lifecycle.py及测试/派生报告。⑥输出创建和adapter构造前校验全部待选F20/MOCK原行：唯一非空ID、BLOCKED_BY_ENV、runtime_invoked严格false、实际runner调用字段如存在亦false、runtime_completed=false、RGBD_CAMERA_REQUIRED原因和合法非空场景/控制模式及严格seed/repetition；重复ID须在count截取前发现。缺字段/原SUCCESS/已执行等全部拒绝。无来源单条初测明确standalone、original ID null，不冒旧行。⑦git_commit(ROOT)，绑定当前实际script与加载adapter路径/SHA，源树外或另一个git cwd结果一致；HEAD不能替代脏源码hash，旧摘要不重写，另附复核。

RED覆盖正确/错误native身份、真实CPU子进程写阶段后异常和信号退出、前置拒绝、prepare参数落地差异、schema-only/缺status/缺prepared文件/真实失败原件、数字布尔、重复/非阻塞/不完整原行、cwd来源偏移。阶段与来源修复不改原运行安全语义。GREEN后重建一次clean wheel，源码树外清除PYTHONPATH/PYTHONHOME测试help/version/validate/doctor/prepare/evidence；同child正确/错误native CPU --help各1次。

0GPU、0renderer、0model load/API、0新增实际lifecycle运行。既有初测1与补充18真实证据沿用，实际18原件仅逐条只读重校验，映射应等于旧summary，勿为修来源重复19次运行。主Phase12runner/validator、adapter执行语义、UTC/native组件、安全阈值与原件不改。两分工不交叉写文件。七项各留RED/GREEN及源码/wheel/来源hash，旧失败与review保留；任何新计划外失败或范围扩大再交实际Astra，不再问既有授权。
