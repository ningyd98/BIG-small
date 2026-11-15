# FrozenPointProvider 阶段身份补充计划

模型：`gpt-6-astra`。**PLAN_ONLY_NOT_IMPLEMENTED**。只计划，不修改实现或测试，不启动模型/网络/仿真。

## 证据与边界

本轮对真实 fixed-042001 做独立只读复证：四次输入同一个 before observation、按序取四个历史phrase，当前provider全部接受，replay_calls=4；记录phase为before/before/post-cloud/post-cloud，但四个current checksum相同。原脚本与stdout保存在 evidence/probe，命令与输入SHA见 plan.json、inputs.json。脚本exit0只表示打印成功，不是负例通过。

根因是phase由调用序号决定，未记录/验证本次运行的阶段身份；暂停仿真RGB、sim_time可保持一致，检查它们不能代替新帧身份。当前单元正例四次同obs及“phase”负例改sim_time，没有覆盖这一要求。

真实生产 `grounded_planner._resume_owned` 在point前调用 `validate_post_cloud_observation`，后者已检查新id/checksum、capture递增及not_before。因此这不是已证的27真实执行路径绕过；它是provider自身不满足原计划独立错phase拒绝的缺口。原生产两文件必须保持字节不变。

## 窄范围修复

仅新增离线模块中的FrozenPointProvider及新增tests文件允许修改；CLI仅绑定输入，不需要改。本轮诊断时点的文件SHA已保存。它们同时处于已授权完整性与fault wrapper修复中，实施前先核对并行diff及更新实施receipt，不用旧快照覆盖新修复。

provider维护本次成功观测身份元组 `(observation_id, frame_id, checksum_sha256, captured_at)`：

- 第1、2次必须是同一元组；第1次完全通过现有输入校验后才记录。
- 第3次的observation_id、frame_id、checksum各自必须不同于before，captured_at必须严格更晚。
- 第3、4次必须是同一新元组。
- 身份、RGB、query、calibration、raw/native等全部校验通过后才递增计数、追加records及提交状态。任何拒绝不消费、不污染状态。

记录当前阶段身份便于审计，保留历史与当前checksum区分。原not_before仍由真实planner检查；provider没有云结束边界时刻，不能编造或放宽它。不要改原RGB/depth门禁、相机或阈值。

## RED / GREEN

1. 第三次重复before：旧实现接受，修复必须拒绝，保持2次消费、2条record，无post-cloud状态；再提供合法新phase可继续成功。
2. 同阶段第二次换obs：相同RGB/depth/sim_time，新合法metadata，第2次必须拒绝且只消费1次；参数化覆盖第4次换obs，保持消费3次。
3. 正例改为before两次、fresh两次。保持原图像、深度、mask、sim_time、相机不变，仅换frame/observation id与更晚capture；清空checksum后用 `RGBDObservation.model_validate` 按实际字段重算。不要用任意字符串checksum冒充合法新观测。
4. 第三次capture相等/更早或任一身份字段仍旧均拒绝；同阶段等值副本允许，不要求Python对象身份。
5. 现有RGB/query/calibration/raw/fullcloud请求差异拒绝继续通过；原改sim_time负例可作为字段一致性测试保留，但不能代替阶段身份测试。

先纯软件RED/GREEN，再新增offline unit（排除实际socket及仿真fault）、现有grounded planner刷新测试和Ruff。合并其他已知修复并通过review后，才统一运行三故障节点及27闭环；本轮单元通过不替代它们。

## 前置与验收

使用shared .venv，启动前PYTHONPATH固定隔离树/src与隔离树；PYTHONDONTWRITEBYTECODE=1，pytest禁缓存，唯一/tmp basetemp。只读V3，输出只在/tmp或新树批准目录。本轮无需EGL/socket提升或模型。

原grounded_planner/revalidation不变；新provider身份保证不声称metadata独立证明物理曝光，真实采集仍由原worker负责。无新增模型/付费/网络/硬件，无改变原27分母、0.1mm/39mm与其他阈值。原计划、原探针、失败字节不可覆盖；新根因再次Astra。
