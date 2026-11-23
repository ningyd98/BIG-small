# Phase 7 教师采集链 E2E

研发基线为 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。本轮检验了停止指令的来源、冻结登记的读回，以及 LIFT 的可观测性。正式 v10 首组沿用 Phase 6 的一次尝试。[主计划](plan.md) · [验证清单](validation.public.json)

## 冻结记录能证明什么

v10 公共读回重建 11,109/11,109 帧，首组有 6,240 个物理步、4 个返回动作、8 条准入。前 7 条允许继续。LIFT POST 的 SafetyShield 允许，随后 `object_lifted` 和 `object_stable` 两个条件未获准入，流程停止。原件的第 428、429 条命令分别为保持和急停，两条记录均缺少可解析的父区间。首组资格为 `UNKNOWN`，其余 8 组为 `NOT_RUN`。[Phase 6 步骤报告](../round-v10-phase6-20261122/step-report.public.md)

v9 使用配对的历史协议和 454 项来源重建 3,373/3,373 帧、2,040 步，首动作 PRE 允许，POST 的 SafetyShield 按原记录给出 `STEP_TIMEOUT`。v10 使用 456 项归档来源，8 次 Shield 和条件决策均逐条回放。整组的两份 JSON 与 Phase 6 逐字节一致。归档入口重新枚举程序文件、验证固定配置和资产、重建协议，并校验来源代。命令行参数 `--source-root` 只适用于离线 `--verify`。[归档读取器](../../../../../../src/cloud_edge_robot_arm/research/native_full_horizon_originals.py)

## LIFT 与 r593

从 4,200 步派发到 6,240 步终止，2,041 个不同物理步位均有原帧。按每步主帧统计，156 步无目标颜色候选，43 步一个，1,839 步两个，3 步三个。43 个单候选样本全部未通过完整轮廓检查。最后一帧的两块候选各有 9 个像素。已解码标记的首末位置给出约 84.8–84.9 mm 的名义升高。登记缺少度量误差界和两次采样之间的运动界，无法据此签发升高下界或连续稳定结论。在线两项事实保留 `UNKNOWN`。[逐步分析与误差条件](vision.public.json)

对同一批冻结帧独立运行两种角点模式，共 22,218 次原检测器调用。两者均通过 10,766 帧，仅 SUBPIX 通过 28 帧，仅 NONE 通过 0 帧，两者均未通过 315 帧。SUBPIX 的 315 帧有 314 帧未解出目标标记，1 帧识别了 ID 7 但尺寸检查失败。标记策略沿用原登记。[按采集角色和物理步的交叉表](vision.public.json)

## E2E 的验证范围

隔离夹具有独立的 release ID、seed、SQLite 和输出目录。真实 worker 取得租约，完成 120 个物理步、采集 124 帧与第一次 PRE/Shield 检查。用例在第一次控制器派发前注入一个故障。基线保存的两条停止命令都指向不存在的 `unbracketed-operations`。候选生成真实终止区间，保持和急停都指向该区间，生效步为 121。SQLite 保留一次尝试和 `BLOCKED_BY_ENV`。相同身份的重试被拒绝，公开读回恢复全部帧，并保留中止结果。[隔离 worker E2E](../../../../../../tests/test_native_collection_stop_e2e.py)

八动作软件正控分别用 v9、v10 数据验证 17 条准入、16 次实际 Shield 调用及 27 条 tracker 时钟。夹具提供终端完成事实和来源边界，替代了物理、操作、几何、物理结果、度量与生命周期阶段。这一正控覆盖完整准入路径。两份冻结实测记录分别覆盖自己实际产生的前缀。[完整软件正控](../../../../../../tests/test_native_registered_admission_replay.py)

第二个真实 worker 测试让外来线程在首个 PRE 后触发制动，同时让合法 worker 退出。原探针中，写者返回前就已开始销毁后端，保持和急停两条都没有写出。修订后，控制写和相应审计结束，worker 才冻结和关闭资源。公共入口重建 124/124 帧并给出 `UNKNOWN`。持续不能完成物理写入的 CLI 另有独立的退出回执测试。[并发制动](../round-v10-phase7-concurrent-stop-20261123/step-report.public.md) · [资源释放和 LIFT 对照](../round-v10-phase7-stop-teardown-20261123/step-report.public.md)

第三种情形在外来线程的 CONTROL 内注入真实写入前的异常。合法 worker 接手后的保持与急停以原序号 3、4 落盘，各自的操作及嵌套 CONTROL 均由同一合法时钟签发。外来来源拒绝、原物理失败、124 帧和部分采集资格均有各自的实测记录。[记录器身份补轮](../round-v10-phase7-recorder-owner-20261123/step-report.public.md)

## 最终研发登记与预检

重新登记了 456 项来源，8 项登记源码相对于正式冻结代发生变化，固定资产哈希逐项一致。最终来源代为 `01f29ebf95837973d52c112d183e11a7abc361a750e42606f1811fad7c9ad04b`。协议文件 SHA256 为 `e5ccd91938aa8b61c158a2bcb644a9dc1c53e31340108d41e09ec87cf105ca5a`。唯一释放项是原登记模板的首组 ID，空登记读回 9 组均为 `NOT_RUN`，开发登记 claim 数为 0。控制器截止步与保持后终步沿用原登记，LIFT 为派发后 1,920 / 2,040 步，RELEASE 为 240 / 480 步，其余六个动作的两项数值相等。[全部动作边界与冻结校验](validation.public.json)

最终单帧检查完成 120 个物理步和两次渲染，生成一帧 320 × 240 的 RGB-D，40,309 个像素有有效深度。r593 检出 ID 7，最短边约 14.25 px，bootstrap 通过，后端正常关闭。控制器派发、教师尝试和正式 claim 都为 0。[可复跑的单帧入口](../../../../../../scripts/phase7/check_development_frame.py)

## 冻结原件

对本轮开始前的输入逐项核验。v10 完整冻结清单有 55,583 项，v9 有 16,885 项。一次对正式数据库的 SQLite `mode=ro` 表结构查询产生了 WAL 和 SHM。核实无进程占用后，将两件派生文件原样移到私有证据目录，保留 inode、修改时间和内容。正式目录恢复原有七项，复验正式数据库 SHA256 为 `09fab63b235ab3317f27b2528aea724015629863fff287496cb45430d23f4b1a`，claim SHA256 为 `6599b24b95016ddddf0ad8df47c3a96d64b13b7eb6fc7abba06809b756ccdee7`。最后在私有冷副本中查到原作业 `BLOCKED_BY_ENV`，尝试次数和上限均为 1。[旁文件复原记录](../round-v10-phase7-new-sqlite-sidecars-20261123/step-report.public.md)

最终完整性检查从磁盘枚举两个正式原件目录，逐文件重算长度和 SHA256。v9 的 2,052,659,909 字节、v10 的 6,578,143,222 字节均与各自冻结清单一致，目录中没有额外或缺失的原件。[验证数据](validation.public.json)

## 最终代码的回归

| 范围 | 通过 | 失败 | 夹具错误 | 跳过 |
| --- | ---: | ---: | ---: | ---: |
| 本轮计划与补轮的专项 | 466 | 0 | 0 | 0 |
| 36 个 native 文件，最终源码 | 878 | 1 | 0 | 20 |
| 34 个 native 文件，原基线 | 771 | 1 | 0 | 20 |
| 21 个相关文件，最终源码 | 677 | 62 | 49 | 0 |
| 相同相关文件在原基线可用的 20 个 | 638 | 62 | 49 | 0 |

专项已包含在下列两组测试里。按用例身份与错误内容比较，最终代码在这 57 个文件里新增失败、夹具错误和跳过均为 0。唯一的 native 失败来自手写 v1 旧原件的 `invalid_action_record:0:semantics`。相邻回归的六个旧 worker 绑定用例在原基线与修订后均报告 observer publication 缺失。在两份隔离源码副本中补齐本机同版 MuJoCo 头文件后，状态守卫测试各 58 项通过。最初因缺头文件出现的 49 个夹具错误和 4 个失败保留在原始统计。[按用例的验证摘要](validation.public.json)

8 个修改过的产品文件在严格 mypy 下各代均有 72 条既有错误，按文件、消息和重复次数比对，新增和消失均为 0。6 个新增脚本与 E2E/视觉测试文件的类型检查通过，18 个改动过的 Python 文件通过 Ruff。独立定向复核在最终记录器上完成，68 项相邻检查通过，三个真实 worker 的落盘结果分别从组和登记两个公共 API 读回。[定向复核和源码指纹](validation.public.json)

## 全仓软件回归

| 完整选择范围 | 总数 | 通过 | 失败 | 夹具错误 | 跳过 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原基线 `2ec0c98f` | 7,519 | 7,015 | 374 | 99 | 31 |
| 收尾候选，三个互斥分片 | 7,636 | 7,133 | 373 | 99 | 31 |

两次均运行仓库软件测试，选择器排除了 Isaac runtime、真实机械臂与外部 RGB-D 数据集。候选分成全部 native、全部 operational 和其余测试三个分片。472 个两边均失败或出错的测试，错误消息在归一化各次运行的临时路径与内存地址后也一致。新增失败、错误和跳过均为 0。带视觉伺服的旧组件诊断在基线全仓失败，在候选分片通过。对该用例单独配对复跑时，基线和最终源码都观察到 `safe_stop → shutdown`，断言同样失败，记录为既有未决项。

全仓分片使用的记录器 SHA256 为 `ed4821583c5399ea2ae70d06713cdf3cec674fd5f0dcd0ff63289331b8b92862`。随后在记录器回调入口增加了实际 owner 检查，并补强两个测试文件。上面的 57 文件和 466 项专项均使用最终记录器 `794f1f19…`。两份完整源码指纹、分片计数、最终差分及按用例比对汇入[验证清单](validation.public.json)。

## 复跑入口

在研发工作树根目录运行。`PY` 指向项目 Python，`PROTOCOL` 和 `ARCHIVE` 指向配对的历史登记目录和冻结源码，`OUT` 为新建的私有输出根目录。带完整原件的机器可从公共 CLI 重建历史组。单独的开发 worker 测试自行准备合成身份、数据库和输出目录。

```bash
export PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=egl
"$PY" -m pytest -q tests/test_native_collection_stop_e2e.py
"$PY" scripts/collect_native_calibration.py --verify --protocol "$PROTOCOL" --source-root "$ARCHIVE" --output "$OUT/replay"
"$PY" scripts/collect_native_calibration.py --prepare-only --config configs/research/native_registered_single_teacher_p0_v10_20261121.yaml --output "$OUT/registration"
"$PY" scripts/phase7/check_development_frame.py --protocol "$OUT/registration" --output "$OUT/frame"
```
