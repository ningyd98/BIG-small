# R500 — 非终态完整原EOS硬屏蔽

实际规划模型：gpt-6-astra；仅规划。完整输入SHA/bytes见plan.json。

已核实际诊断：第26token、target_label开引号处native_accepting=false，原EOS[248044,248040,248046]的mask=[0,200,0]，guard正确报错，模型仍0load/gen。批准补全原计划要求的非终态EOS硬禁；native列出三EOS不代表mask已履行HF停止语义。

新byte_decoder_r500.py保留所有原代码/失败副本；复制native mask后先禁精确28项D，再仅在matcher.is_accepting=false时把原三EOS全部置0。每步记录native接受态、原EOS mask、suppressed列表与有效mask/hash；cache、consume前检查、callback和最终membership统一使用此有效mask。终态不注入任何token、不补native禁止的EOS，仍要求原生三EOS全部可达；不修改HF配置、库、tokenizer、schema、输入、D或依赖。

新CPU报告完整重放原21项及27个ASCII存在性见证；确认旧开引号状态248040从200变有效0，所有非终态三EOS全禁、合法终态native三EOS原已可达，且原byte/special/Unicode/尾反斜线/前缀/重复回调/跨请求/空mask门槛不变。禁止按文本猜终态、force EOS、忽略错误。CPU全PASS并满足R497codec/72包、R494环境/真实硬件和GPU准入后，才运行原八次A，无warmup。

只从原A空余预算再拨最多5分钟：CPU至 **15:48:20 UTC**，本次gate≤120秒；原整体 **16:19:20**、A16:00/B16:04:20、1load24gen不变。终态缺EOS、未知失败或超时即冻结最终负结果，不继续扩大适配。保留生成序列子集声明和全部旧失败，软件/真实/质量/正式验收分列；交付沿用原R491显式路径与三SHA。
