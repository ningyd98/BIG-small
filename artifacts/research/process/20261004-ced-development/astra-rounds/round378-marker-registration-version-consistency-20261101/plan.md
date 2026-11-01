# R378 Marker Registration Version Consistency Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 执行；用户已授权恢复登记一致性，无需追加设计审批。

**Goal:** 新建 development 登记版本，使两组 marker 测试真实进入候选及反例逻辑，同时保留旧 v1 的正确拒绝。

**Architecture:** 依据精确旧源码快照与当前源码的差异、未变几何和真实重放创建 v2，不覆盖 v1，不改产品。版本登记只产生 DEVELOPMENT_ONLY 诊断证据。

**Tech Stack:** 现有 Python/pytest、OpenCV/PIL/numpy、PyYAML、CPU MuJoCo 等价性检查。

**Spec:** 用户恢复测试输入与来源版本一致性的授权、根 AGENTS、同目录 plan.json 的完整 diff/pins/命令。

## 原失败与源码审查

共 **44 原失败**：R373 software05 的36项、R374 software06_remaining06 的8项，均在 strict source binding gate 拒绝，尚未运行后续候选/反例断言。旧 JSONL/日志/JUnit（若存在）以及缺失输出如实记在 JSON，不补造旧结果。复用44项为 RED，不再重跑旧失败。

v1 配置 SHA `209a133c05d5b98f940bf9467133ea24120cbb946083dbbb80309cc022172605`。六项绑定只有 marker_association.py 从 `f538c6b751ab560b2523cfbe2d237f8956b092931af276bfcda744d10ee4f426` 变到 `3fb8c53681b5140c121f45c4d378fbe6b3b5ba5d7daee09fef696cf38bf8238a`。已找到完全匹配旧 SHA 的 `t7b-marker-extent-next/fix-round-1/source/src/cloud_edge_robot_arm/vision/marker_association.py`，不是猜测旧版本。

精确 diff 仅含：context 可选 operational_reference 及冻结；None 时摘要省略该字段保持旧形状；frame context 获取描述引用；live freshness 接 operational_windows。无活 owner 时引用为 None，development replay 仍使用原 captured_at 并不调用 live reference 判定。几何/颜色边界算法、source/path 检查和 admission 规则没有改动。该静态证据只支持申请新版本，不能替代重放验收。

## 新版本与最小文件范围

新增 `configs/research/ced_marker_registration_v2.yaml`：registration_id=`ced-marker-color-v2-object-development-v2`，schema 仍 `marker.object.registration.v1`，admission_scope 仍 DEVELOPMENT_ONLY。**相对 v1 只允许 registration_id 和 marker_association.py 对应 SHA 两处语义差异**；六项集合及其余五项 hash 不变。

几何保持：ID7、DICT_4X4_50、45mm marker、35mm object half extent、z=35.05mm 附着，tag/quiet/face 半边长22.5/30/35mm。标记 XML SHA `2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4`，基础 scene SHA `66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`，均不改。

两消费者 `tests/test_marker_association.py`、`tests/test_marker_extent_integration.py` 只切 CONFIG 与实际 loader 的预期 SHA，预期值在 v2 落盘后固定为字面量，不能运行时自刷新。association 模块新增两项同根因回归：旧 v1 在当前源码根下仍拒绝；新旧配置只差允许两处、真实新 loader 成功、交叉使用旧/新 registry SHA 均拒绝。原全部断言、时间/几何阈值和反例保持。

## 实施与运行

- [ ] 在前序整批结束、进程清理及单写者交接后复核 50 项直接 pins、六项绑定及帧原始来源。R376/R377 的独立测试/console 改动不列为本轮依赖，不误报漂移；记录其后实际 HEAD。
- [ ] 保存精确旧→当前 diff、几何/配置比较；创建一次性 v2，更新两消费者与新增版本回归。源代码、v1、旧帧/资产不变。
- [ ] 一次完整两个 marker 模块 GREEN，300秒；包含原44案例及新版本回归，不能只验证 hash 或选择正例。
- [ ] 一次完整 `tests/test_pose_marker_evidence.py tests/test_pose_marker_assets.py`，180秒。覆盖旋转/模糊/校准/深度拒绝、原分辨率帧、tag/红色可见支持、XML visual-only 添加、CPU 编译后动力学/相机/控制器/接触等价。无需渲染或重新采集。
- [ ] 新失败保留、暂停相关修复交下一轮 Astra，不改阈值或追着更新 hash；独立 guard 阶段仍可完成。零自动重试，不并行。
- [ ] 校验全部原源/帧/资产/v1 前后 SHA，保存 stdout/stderr/JUnit/退出/耗时/清理/覆盖表/步骤报告；只选择已验证 v2、两测试改动及精选证据提交推送并核对三 SHA。保留用户其他脏文件，不广泛 staging。

精确命令见 JSON：现有 .venv，禁用 pytest 自动插件与 cacheprovider，各有独立 basetemp/JUnit/cache。300+180+两次15秒清理=**510秒**，本轮总墙钟**900秒**；可选一次30秒 collect-only记录新计数。TERM宽限5秒、所属组回收，剩余预算不足则不启动。不与 R376/R377 测试或源写入并发，不切工作树/安装依赖。

## 帧与验收边界

STATIC 时间 `2026-10-04T13:58:29.655538Z`，INITIAL 时间 `2026-10-04T14:22:40.829889Z`，source 均 `mujoco_camera`，calibration `3a224602f7d34743`。JSON中列出完整帧/metadata/RGB/depth pins及额外 guard 帧。不得重写时间为当前、伪造新拍摄/标定/来源，不把 instance_geom_ids 或 simulator truth 当关联输入。编辑RGB/depth仅为原测试限定反例，不能升级物理证据。

两个原帧须真实到达 OBSERVED_CANDIDATE/DEVELOPMENT_REPLAY，同时 NOT_ADMITTED、whole identity UNKNOWN、extent_complete=false、误差/运动/角速度界 None、稳定性 UNKNOWN。历史帧 live freshness 仍拒绝；原 path/symlink/source/hash/admission 拒绝与篡改/缺深度/外边界反例全部执行。原44案例、新guard及必要 pose/evidence/asset回归无新增 skip/failure/error/timeout才闭合。

v1 继续拒绝当前不匹配源码是预期安全行为，不能将其改成兼容成功。本轮不是仅刷新 hash，也不声称 native/physical/full-extent/正式研究验收。实际执行权限需重新记录，环境拒绝不当产品失败。保留 local_temporal候选、两份未跟踪 temporal 测试及嵌套 workspace，不纳入交付。

规划者实际 `gpt-6-astra`；仅只读调查与写计划，未导入产品、运行测试、发送信号、联网或使用 Git。
