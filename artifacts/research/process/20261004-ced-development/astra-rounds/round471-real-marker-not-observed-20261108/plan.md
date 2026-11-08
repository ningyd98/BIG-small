# R471 真实 marker 未检出：限定离线像素诊断

规划者：实际 `gpt-6-astra`。PLAN_FROZEN_DIAGNOSTIC_ONLY_NOT_EXECUTED。本轮只释放一次CPU离线诊断，新增actual/API/physics/render/GPU query均0，累计真实尝试仍为2，不授权第三次实际运行。

## 原始证据与已知边界

R470监督正常退出，child rc1，reaped=true/remaining=[]/supervisor errors=[]，source unchanged，28.5637秒。产品COLLECTION_PARTIAL，completed_action_count0、physics120、render367 EXACT。primary为`registered marker unavailable: known_marker_not_observed`，worker_terminal FAILED为后续结果。独立read rc0，123帧重建，9组score和joint_bound均null；原647文件90728782字节读前后不变。R468原失败保留。

当前detector仅当OpenCV ids=None才产生known_marker_not_observed；错误在min-side/depth/size/pose检查之前。生产在120 settle后boundary acquisition-123引导grounding时停止。直接查看其320×240原PNG，确有很小黑白marker位于红cube旁；约9px的视觉估计不是可观测性或根因证明。冻结XML为ID7布局、0.045m六格内边/0.060m quiet region、顶视320×240/fovy50。候选缺失、位图采样/aliasing、quiet border/照明、XML位序或OpenCV版本行为均须分辨，当前不允许调参数或改资产。

HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`；423项source_generation `e5795af5d1a7b90a7dcb442da0f37c0ec9fe4fad04d13e3696c4a5cf609fdd55`。plan.json冻结全部源码及58项失败/协议/帧/blob/配置/源码输入SHA。不得读DB内容。独立reader `_Audit.domain` AttributeError另列deferred新根因，不混入本轮、不改原报告。

## 限定诊断

ROOT只实现本轮 `implementation/diagnose_marker.py`，静态AST/JSON/hash核查后冻结SHA。选择原acquisition-1、61、121、123，逐帧核对inventory/file_hashes、base64 encoded_string哈希、完整payload SHA与RGBD模型roundtrip；恢复原captured_at/checksum/intrinsics，不改clock。只导入纯RGBDObservation/PoseMarkerRegistration/detect_pose_marker，不导入应用/reader/backend；明确禁止simulation、MuJoCo、cloud、网络模块/调用。

每帧一次原生产detector（最多4次），再同全尺寸原RGB灰度、同默认参数/errorCorrectionRate0的OpenCV候选统计（最多4次）。123必须复现UNKNOWN/known_marker_not_observed，否则记录分歧停止，不修/不重试。保留accepted IDs/corners、rejected candidates/边长、灰度像素与版本。所有候选取自像素，不用scene/physics/instance truth填角点或可见性。

纯XML抽取36格/RGBA及quiet rectangle，与唯一generateImageMarker(DICT_4X4_50,7,6)字典位图比较。将此合成位图按每格20px、white margin20px构造一次reference并运行同decoder（最多1次），只验证环境/字典，不视为真实帧通过。原图可作带来源SHA的crop/nearest-neighbor展示，123固定可视crop[184,108,210,134]；任何crop/放大/warp都不得再送detector获取通过，也不得写回raw。

最后给各假设SUPPORTED/REFUTED/UNRESOLVED及证据。XML匹配不证明实际光栅正确，合成reference成功不证明真实可观测；没有足够证据时明确未定。禁止阈值扫参、其它dictionary、真实图上采样通过、truth fallback或全局放宽detector。

## 精确命令与资源

工作目录 `/home/ningyd/文档/ChatGPT/BIGsmall`，清洁CPU env见plan.json，CUDA_VISIBLE_DEVICES空、cv2 OpenCL关闭、线程1，仅限制离线资源不变detector参数。

```sh
/usr/bin/timeout --signal=TERM --kill-after=5s 180s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round471-real-marker-not-observed-20261108/implementation/diagnose_marker.py' --plan '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round471-real-marker-not-observed-20261108/plan.json' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round471-real-marker-not-observed-20261108/diagnostic'
```

child wall120秒/outer180秒、RSS2GiB、输出256MiB、free≥1GiB、一次/retry0。ROOT保存stdout/stderr原始字节、rc、UTC/monotonic与hash；脚本不生成子进程，wall alarm/逐步资源检查，外层timeout收尾并确认reaped。source/raw前后SHA不变。任何异常先保全、下一实际Astra再处理，不重跑。无新增software tests、引擎、渲染、服务或GPU诊断。

## 后续修复门槛

本轮没有产品/测试/资产修改授权。诊断证实根因后由下一实际Astra限定具体修复与必要RED→GREEN，包括原真实帧及foreign/ambiguous/undersampled/occluded反例，保持原freshness/depth/authority。若必须新asset/registration，另轮明确版本化，旧scene_pose_marker_outboard_v3、grasp_v2、硬hash与raw永不改；继续保留用户marker7/顶视camera/controller/OpenCV。根因仍是假设则先下一轮有限诊断，不盲调。

R469 P1在本轮source不变时仍只能按自身精确pins/前置条件推进；任何未来src/config/asset修改会使其冻结失效，必须暂停并由实际Astra重新冻结新来源和命令，不能重贴旧hash。P1密钥不阻塞本离线诊断。

验收仅为离线复现、候选/像素/字典证据及清晰根因结论或未决状态。native UNKNOWN、formal NOT_ACCEPTED，真实attempt仍2。取得可review诊断/修复后才另行讨论第三次actual边界。提交推送仅本轮脚本/诊断/派生展示及明确清单，raw/DB本地保留；核对本地/上游/远端SHA。

本规划只读代码/JSON/原PNG并查看图像，没有运行detector、软件测试、引擎、渲染、API或GPU查询。

补充输入：R470 implementation/step-report.md/json已冻结SHA，记录12次限定ENOENT、owner closure完成、最大采样间隔0.500085秒、累计2attempt与读后原件不变；本轮问题独立于已处理监督竞态。

静态依赖补充：原RGBDObservation导入simulation.models中的SensorFrame，因此仅允许simulation包空初始化与simulation.models纯dataclass模块；其它simulation backend/controller/runtime仍禁止，不构建SensorFrame或引擎。此白名单保持生产decoder原样可导入，不授权任何仿真调用。
