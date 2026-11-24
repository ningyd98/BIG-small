# 径向装配错校准见证与零步资质

+15 mm 装配通过四项原生零步复位和 11 个负控。三个可见场景向控制器提交了与当前 RGB-D 包一致的目标。全遮挡场景收到一个保护保持指令，四个场景合计运动指令 0、物理步 0。两次独立读取四个原包，结果逐字节一致。[终验摘要及 100 份私有原件的 SHA256](qualification.public.json)

## 修正范围

旧预检在双码可见时通过 12 项检查。随后 11 个负控中的 10 项通过，错校准项保存了相机、目标和伺服的实际拒绝，诊断判为未证明。旧验证器原本识别已绑定跟踪器更新时的 `registered collection geometry unavailable: observation_calibration_version_changed`。径向预检在首次绑定当前包时由原生跟踪器提前给出 `initial registered geometry unavailable: registered_camera_mismatch`。两条路径的伺服拒因均为 `servo MuJoCo calibration does not match frame intrinsics and pose`。首轮留下的 53 份文件全部复核原始摘要，失败生成代保留原来结果。[首轮失败原件](../round-g1-visibility-approach-geometry-20261125/runtime-first-preflight.public.json) · [专项计划](plan.md)

径向适配器对错校准项重算两个文件摘要与原生 RGB-D 校验和，逐字段比较原包和测试包，验证观测身份与实际拒因。仅校准版本、帧和观测 ID、重算校验和四个字段发生变化。实际相机、捕获钟、场景、回合、深度、像素、掩码和内外参一致。两处目标拒因各按精确原文验证，另核伺服与目标均拒绝、未接受样本、无命令和零物理步。其他十项维持原有判定。旧程序的拒绝判定与新见证同时入档。本轮发布的 565 个源和资产文件中，仅径向诊断适配器内容变化。[现场负控和历史双姿态原始见证](qualification.public.json)

实施前验过计划的 29 项输入。保留的软件 RED 先在原包上复现旧判定，随后 97 个回归测试通过。测试覆盖两个已有的原生拒绝位置，以及错场景、过期、遮挡、歧义、错几何、错来源、缺少拒因、互换包、错误校验和或产生动作。另从两个历史零步姿态各自的原始 RGB-D 文件、轨迹和结果交叉验证，分别通过同一新见证。[RED 输出](calibration-red.stdout) · [回归输出](calibration-software.stdout) · [修改前测试字节](previous-radial-tests.input)

## 选定装配与实际预检

复核选型资料的公开及逐帧摘要。两种深度观测下，22/22 个历史静态锚点合格，包含旧正式八组的历史拒绝帧及前一帧，以及 d02 第 1088 步。该步只凭可见的 ID7 得到注册抓取点。d01/d02 原轨迹共 2,210 个冻结状态通过净距检查，手或手指距支架最小分别为 5.249 mm 和 45.214 mm。两侧标记中心距由原 100 mm 增至 115 mm，本代编译质量 0.10102432 kg，评分程序逐码反解登记的刚性变换。[光学筛查](../round-g1-visibility-approach-geometry-20261125/screen-optical-15-summary.public.json) · [净距筛查](../round-g1-visibility-approach-geometry-20261125/screen-clearance-15-summary.public.json) · [机械选型](../round-g1-visibility-approach-geometry-20261125/screen-selection.public.json)

| 现场复位 | 当前标记与选择 | 原生检查 | 当前运动目标修正 | 后端命令 |
| --- | --- | --- | --- | --- |
| 两码可见 | 7、8，选 7 | 12/12 | 0.184 mm | 0 |
| 仅 ID7 可见 | 7，选 7 | 12/12 | 0.184 mm | 0 |
| 仅 ID8 可见 | 8，选 8 | 12/12 | 0.341 mm | 0 |
| 全幅遮挡 | 无目标 | 10/10 | 当前帧拒绝 | 1 次保护保持 |

四个独立作业都在首次尝试关闭并释放租约。每次在既定姿态 `[0.45, 0, 0.035, 0]`、种子 `24113040` 启动。三个可见场景的生产 LIFT 目标也均保持固定。11 项保障负控全部拒绝，其中三项由注册资产、刚体变换和来源约束直接阻断。两个独立进程从匿名原包重新读像素，分别核对非空目标与逐码反解的一致性。两份四帧封存 SHA256 同为 `187845a0105b49e12dfe87c030511c42a1258a612b12d72c0c467e9032013bd3`。[四场景原件清单和逐项拒因](qualification.public.json)

同一顶视相机使用原校准 `f33940579c533afe`、RGB-D 320×240。运行使用 EGL 独占、Python 3.12.3、MuJoCo 3.3.7、OpenCV 4.14.0、NumPy 2.5.3 和 Pillow 12.3.0。预检结束时磁盘可用 76,032,827,392 字节。注册对应 495 个目录条目，运行记录了 231 个已导入项目模块。前后复核 919 个正式原件及其中已有的 8 项登记。[运行环境及原件摘要](qualification.public.json)

## 构建与交接

工作树为 `/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-v10-phase2-20261121`。实际运行的构建和预检命令如下。[构建输出](prepare.stdout) · [预检输出](preflight.stdout)

```bash
env MUJOCO_GL=egl /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -B -m scripts.graduation.g1_visibility_trials prepare --radial-mm 15
env MUJOCO_GL=egl /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -B -m scripts.graduation.g1_visibility_trials preflight 36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf
```

- 构建 SHA256 为 `36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf`。
- 预检 SHA256 为 `90a4c0ed2ab0370e426acefabfc8eb1f991139c7b9178e0c654cf31df6a7723a`。
- 全部私有零步原件位于工作树 `experiments/results/g1-visibility-pose-repair-20261124/builds/36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf/zero-step-radial-e5yo9ao2/`。公开结果 SHA256 为 `7c04db96abc3f41fcacc745963e451898677808649dbc67025ef8d81093bb2b0`。[逐文件清单](qualification.public.json)

历史开发唯一 d02 由运行负责人随后签发，批次 `train-radial15-01`，分配 SHA256 为 `43bcb255003c2d0071604a31c671f4b9af17fc4c74bab31d2e0e06ee71221c16`。原生动态和独立评分随机械轮次归档。[试次及两次独立评分](../round-g1-visibility-approach-geometry-20261125/radial15-d02-outcome.public.json)
