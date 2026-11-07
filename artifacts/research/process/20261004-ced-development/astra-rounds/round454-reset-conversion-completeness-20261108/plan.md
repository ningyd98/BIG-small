# R454 — RESET 转换完整性首步拒绝补漏

实际模型 gpt-6-astra，2026-11-08。仅规划；未运行测试、physics、render 或模型调用。本轮原始证据是静态源码，不虚构运行失败。冻结输入见 `intake/input-pins.json`（24 份完整字节副本），逐行原片段见 `intake/static-evidence.txt`。R453 final-focused 在收到任务时仍运行；不取其未完成输出为固定输入，不改产品直至其退出、回收并独立保存结果。

## 证据与根因

旧 raw_recorder_v3._record_frame 调原 observation_from_sensor_frame；RGB 字节数不等于 width×height×3 会触发 ValueError。旧 recorder 捕获后将实际 acquisition interval 标成 ABORTED/error，仍追加 observation_payload=None 的帧，没有追加 audit_failures，也没有抛回 backend。新 recorder 可保存这份空帧元数据、instances、source hash 和 capture receipt；backend CAPTURE END 的 error_type 仍为空，返回的两个 pass 可正常计账。require_clean_reset 现检查外层失败数组、RESET 元数据、CAPTURE/source/inventory 和 exact=2，却不检查这份原 acquisition disposition 与 observation payload。因此正常 backend bracket 不足以证明转换成功。

这是 R452/F2 同一“首步之前不能遗漏已保留来源失败”的漏检分支，不是新转换规则，也不重新设计 recorder/backend。F5 已返回 pass 计数保持原语义。

## 最小范围与实施

只允许修改 `src/cloud_edge_robot_arm/research/native_full_horizon_recorder.py` 的 require_clean_reset 及必要局部导入，和 `tests/test_native_observer_failures.py` 的新增节点/必要局部测试复用。旧 converter/raw recorder/backend、shared helper、app、reader/kernel 均只读。不得把失败数组补成替代原记录的假证据，不能把 ABORTED 改为 RETURNED、删除坏帧、重采或修复输入字节。

1. 先复核全部冻结 pins；仅报告文件的正常追加不能被当作产品漂移豁免。若 R453 final 出现新失败，按 AGENTS 分别处理，不能以本轮小回归替代其 gate。
2. 增加 `test_reset_conversion_failure_vetoes_first_step_and_keeps_original`。复用现 SOFTWARE_ONLY backend、真实 RESET wrapper/body、真实 recorder callback、原 converter、原 app.execute_once/worker 关闭链。仅在 fake camera 返回真实 SensorFrame 后用 dataclasses.replace 将非空 rgb 截短一字节；其余字段、原 pass_state_hashes、真实帧 ID/时间等保持。不要 mock converter、require_clean_reset 或伪造 ABORTED 行。沿现测试将 initialize 替换成软件模型/相机装配，将 guard 入口设成记调用并抛 RuntimeError 的 sentinel，step/sampler 设为禁止调用，确保无 MuJoCo 初始化/实际步进/render。
3. 新节点在 guard 之前的 require_clean_reset 入口读取实际 recorder 状态（只读测试观察器可委托原方法）：证明 failures/audit_failures/backend observer arrays 都为空，CAPTURE 外层无错误，真实 acquisition row 为 ABORTED 且包含 `RGB size must equal width * height * 3`，source-frame 的 observation_payload 为 null，exact pass=2。这证明本轮覆盖此前未覆盖的路径。随后调用原 require_clean_reset，不在测试观察器替产品拒绝。
4. 唯一 RED 预期该节点 assertion 失败：旧检查使 guard sentinel 被调用，调用序列为 reset→guard，而期望仅 reset。原 converter 的 ValueError 被保存且不会直接抛出；不把 import/setup/异常类型不符计作预期 RED。测试先验证原错误/软件环境，再断言首步拒绝，以免空路径通过。
5. 在 require_clean_reset 已有唯一 CAPTURE 约束后，通过该 operation_id/acquisition_id 精确查找原 `_operations` row、`_intervals` 和唯一 `_frames` 记录：同一 `operation-N`、kind ACQUISITION、RETURNED、error=None；frame 的 acquisition_id/interval_id 同源，live observation_payload 非 null 且有真实 observation_id/checksum。校核该 aid 对应的库存 source-frame 元数据 observation_payload 非 null、相同身份及 interval；沿原 inventory 哈希校验，不能用未验证外部路径。可在现 inventory 读取循环中保留此单份 JSON，避免重复全库存读。成功帧 live payload 已缩为两个身份字段，这是实际 streaming 约定，不要求把全图重新装入内存或再运行 converter。缺失、重复、ABORTED/error、null 或交叉 identity 均抛清晰 `reset source ...` RuntimeError，保留原 conversion error 在原 interval，必要时拒绝消息引用它。不得以外层 CAPTURE error_type=None 覆盖内部失败。
6. GREEN 新节点验证调用仅 reset、无 guard/sampler/step，collection-result 为 COLLECTION_PARTIAL/physics_steps=0、owner 关闭完成、worker 保留首步来源错误；partial-originals 保留 ABORTED/原 ValueError/source-frame null。软件返回的 pass 仍 exact=2，不因拒绝改成0或null。现 clean 对照继续到达 guard sentinel；既有 write/observer/audit/camera 五变体、已返回 pass 与未知 pass 测试保持。

## 唯一有界验证

所有展开模板已落盘 `spec-templates/*.json`，使用新 R454 runner + 原 R413 bounded_stage，新 basetemp/目录/env/JUnit/events，不覆盖任何旧规格或结果。实现阶段只允许对两个批准路径一次必要 import sorting/format，不改其他文件。执行顺序：

- conversion-red：只跑新增节点，预期恰 1 FAIL，确认实际触发上述行为。
- 完成最小补漏与格式化后 conversion-green：只跑 tests/test_native_observer_failures.py，预期 4 PASS（原三节点+新增一节点）。这是改变 RESET 准入的直接依赖验证，不再跑 R453 final-focused 或整仓套件。
- ruff check 两个路径、ruff format --check 两个路径、mypy --follow-imports=silent 新 recorder，各一次。

每阶段 child≤120s/outer≤240s，attempt=1、串行、全软件；任何计划外失败/新增根因/范围扩大立即停止依赖修复并新 Astra。无额外 probe、collect-only 或 retry。保存原 stdout/JUnit/events/result、前后 SHA/diff 和 implementation/step-report。R453 已通过结果保持历史，不冒称它覆盖尚未实现的 R454。

## 放行边界

验收是首步拒绝真实 converter 失败并保留原件，以及四个直接相关软件节点和限定静态通过；不等于 full-H/native/正式研究通过。交给现 whole-change reviewer 的 scoped follow-up 包含本遗漏，不新开 whole review。未来未运行 prepare/full/read 的新 runner/source overlay 必须追加 R454 批准差异与最终 SHA，保留旧命令/结果；fresh prepare 仍必要。R450 服务授权独立等待，未授权不得停服务。

实际额度完全不变：首组 seed439001 一次；physics≤12960、explicit≤12976、implicit≤12962、render≤64852、wall1800s/outer1920s、RSS8GiB/raw16GiB。本轮 actual=0，不增加九组或模型费用。当前完整实际来源仍 NOT_RUN、native UNKNOWN。

自审：静态问题与运行证据分开；原转换器真实触发；最低层 ABORTED 不丢失；返回 pass 不回退；不改变旧 schema/controller；仅两路径、一个新增 CPU 节点和直接受影响三节点回归。
