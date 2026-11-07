# R448 — 注册像素夹具与真实检测路径一致性修复

计划模型：**gpt-6-astra（实际 Astra）**。日期：2026-11-08 Asia/Shanghai。状态：仅规划，未实施、未运行测试；physics=0、render=0、模型请求=0。

## 原始证据与边界

R447 修复回归已经结束：**228 PASS / 2 FAIL / 2 deselected**，pytest 67.34 s，监督器 68.061202899 s，子进程 rc1，reaped=true，无 source drift、残留子进程或端口。R447 ruff、format、mypy 子进程均 rc0。这两个失败都是原 R446 节点，在 B 的真实 bootstrap 内报 `registered marker unavailable: registered_marker_size_inconsistent`；后面的时序、像素、独立重算断言尚未通过，不能用前面 228 项代替。

原 stdout、stderr、JUnit、events、result、spec 与相关源码均逐字保存于 intake；`inputs.json` 和 `plan.json.input_pins` 记录 **34 个输入的 SHA256/字节数/原件副本**。所有旧结果保留，不覆盖、不清洗。规划过程仅做文件读取与标准库算术/哈希，没有运行 detector 或项目代码。

## 根因和精确修复

旧 detector 没有设置角点 refinement；它真实解码 ID7 后，在各角点及中心取四舍五入坐标的 3×3 深度中位数，要求最短边至少 8 px，metric 边长相对 .045 m 不超过 30%，并要求角点/中心共面误差不超过 .002 m。

现 fixture 12×12 图块落在 `[114:126,174:186]`，只把同一块深度设为 1.32995 m，外侧全为 1.4 m。边界角点 3×3 patch 多数落到背景；11 px 边对应 0.05984282 m，高于 .0585 m 上限。即使只解决尺寸，角点 1.4 m 与中心 1.32995 m 也会触发下一道平面门限。这是合成 RGBD 的采样不一致，不是 detector 或物理注册错误。

仅允许修改 `tests/test_native_collection_grounding.py`：

1. 保留 BITS7 原 6×6 bits、注册 camera、marker id7/.045 m/offset、中心 `(179.5,119.5)`、红色目标/绿色目标区及全部时序/lease/source 值。用 `Image.fromarray(BITS7).resize((10, 10), resample=Image.Resampling.NEAREST)` 得到固定 10×10 glyph，放入 `image[115:125,175:185]`。不模糊、不抗锯齿、不据运行结果自适应调参。
2. 将同深度白色 quiet zone 覆盖扩为 `depths[112:128,172:188] = 1.32995`；RGB quiet zone 仍为真实白色像素，其他深度不变。它完整包含角点与中心的 3×3 patch。名义投影边长为 8.70735 px；新图块角点边长约 9 px，对应 0.04651244 m，处于原门限内且远离旧上界。尺寸离散化仍是 SOFTWARE_ONLY 测试图形，不是新增标定证据。
3. 在现有正例 setup 或首个节点中补充 fixture 自检，**不新增 collected test**：对 B/E 的原 RGBD 字节调用未修改 detector，断言 OBSERVED/id7、最短边≥8、metric 边在原注册区间内；以真实返回角点及中心读取深度，断言各 3×3 patch 的全部值都等于 float32 的 1.32995。保留 detector 的误差界 None、稳定性 UNKNOWN。随后照常执行真实 bootstrap，不替换 detector、bootstrap 或 tracker facts。
4. 两节点原有 B/R/E、绑定、同 step、独立 reader、缓存 identity、缺 marker/region、时间倒置、重复/陈旧/未来帧、写失败和 changed payload 断言全部保留。后续任何失败不得归入“预期”或改断言绕过，需停止交给下一轮实际 Astra。

明确禁止修改任何产品模块、camera/asset/marker 注册或旧门限，禁止把 fixture 变成假 OBSERVED 数据，禁止新增模拟器、render、云模型或在线资格。源 generation 不变。

## 唯一实施与验证路径

实施前逐个重验 34 个输入；任何非本范围漂移先判断适用性。完成单文件修复后仅允许一次格式实现命令：`.venv/bin/ruff format tests/test_native_collection_grounding.py`。随后生成冻结 post-edit pins 与全展开 runner/spec，沿 R413 bounded_stage、r413_events、r235_startup_prerequisite。新目录全部位于本轮 validation，不复用旧 basetemp/cache/log/result。

`plan.json.verification_specs` 已给出完整 argv/env/路径模板，顺序为 ruff → format → pixel-repair。每个只运行一次，child timeout120 s，outer240 s，任一步失败即停止。CPU 修复仅有以下两个节点，预计 **2 PASS / 0 FAIL / 0 deselected**：

- `tests/test_native_collection_grounding.py::test_original_registration_requires_new_first_dispatch_frame`
- `tests/test_native_collection_grounding.py::test_registration_handoff_rejects_backdating_and_stale_capture`

不做 collect-only、单独 detector probe、再次 RED 或 230 项宽回归；不重跑 mypy（产品未改变，测试文件不属于原 mypy 范围）。ruff/check 与 format/check 只针对唯一改动文件。Runner 应冻结 post-edit 源和 spec 哈希并保存原始 stdout/stderr/events/JUnit/result、前置条件、退出/回收/漂移/端口记录；源文件在各阶段期间保持不变。

## 验收与续接

两节点必须真正走完原 R446 所有目标断言，静态与软件阶段子进程均 rc0、reaped、无漂移/泄漏。其余 228 个 PASS 在产品与各自输入未变前提下沿用 R447 证据；报告须写“R447 的 228 个未受影响 PASS，加本轮 2 个修复 PASS”，**不得声称本轮新跑 230 PASS**。两个原 deselected 真实节点仍未运行。

本轮零实际额度，原 R439 一组 prepare/full/read、独立 reader、全部资源上限和九组禁令均保留；通过后仍须新鲜 whole-change reviewer，再按已批准原运行条件推进。旧 raw/UNKNOWN 不改，软件通过不构成 full-H/native 证明。若最小固定 raster 仍无法解码或后续目标检查失败，保存新原件、停止，不再改参数重试。

自审：原失败已结束且完整保留；一处 fixture、一项同根因；无产品行为改变；两节点预算明确；未以原 228 PASS 冒充被阻断路径的验证。
