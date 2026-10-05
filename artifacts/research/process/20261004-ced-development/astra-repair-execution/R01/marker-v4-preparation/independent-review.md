# R01 marker-v4 preparation independent software review

**Decision: REQUEST_FIX — R01-V4-RANGE-01.** 当前 frozen pilot 尚不能据此执行 root 唯一 actual fresh sparse pilot。仅有一项 qualified 行为缺陷：固定原配方范围为 4806 个 physics steps，实际终点为 4807 时，现有 sparse 终态仍标为 COMPLETE。没有修改实现、旧原件、源档案、报告、rootdocs 或 Git。

本次范围是 QUIET preparation 的软件执行路径、冻结来源、XML 差异、固定 sparse 分母、guard 委托、失败封口及原配方范围完整性。执行了 owned 34 CPU 的独立复跑、定向静态检查、来源/分母/XML CPU 控制与一个真实 recorder CPU RED。没有构建或调用模型、backend 实例、renderer、physics、decoder、provider 或硬件；runtime 校验只有实际模块导入，MjModel/MjData 实例为 0。`pilot-protocol/attempt-1` 检查前后均不存在。

## 唯一 qualified 缺陷

`run_sparse_once.py:163` 的 `SparseRGBDRecorder.finish()` 把 callback 连续性及实际 `final_step + 1` 作为完整性条件，没有绑定 frozen header 的原范围 4806；`run_sparse_once.py:299` 的真实 recorder 注入也没有传入该范围。`run_sparse_once.py:378` 冻结 expected=4806，但下一行显式关闭 admission gate。作者 plan/report 如实称其为 forecast，这不是伪造原报告；它与 root 本次要求的“原范围诊断完整性合同”不一致。

CPU 反例读取原 frozen header，经 `configured_runner(header).StepRGBDRecorder` 使用实际注入类，不改任何 selection IDs，使用明确的 CPU observation fixtures，不冒充 MuJoCo 输出。完整可复制脚本及 stdout/traceback 保存在 `independent-review.log` 的最后一个 `QUALIFIED_RED_SCRIPT_BEGIN` 段；首次 probe 的错误 gap 键仅是未合格 fixture 错误，已明确标记并修正，不计为缺陷。

| 同一 frozen 201-step 选择 | 原范围对照 | 多一个物理回调 |
| --- | ---: | ---: |
| 实际 final_step | 4806 | 4807 |
| 保留 PHYSICAL_CALLBACK | 4807 | 4808 |
| allocated/saved selected RGBD | 201 / 201 | 201 / 201 |
| missing selected steps | 0 | 0 |
| 当前终态 | COMPLETE | **COMPLETE** |
| 范围合同应有终态 | COMPLETE | INCOMPLETE 或 RECIPE_DEVIATION |

额外 step 4807 的 callback 完整保留且 selected=false；201 原始编号未迁移、没有删帧。要求 deviation 不得 COMPLETE 的断言得到 exit 1，健康对照通过。此 RED 证明实际 recorder 的范围终态缺口，不声称实际轨迹已发生偏离。

最小修复应让新的 frozen header/recorder finish 绑定原配方诊断范围，并使偏离有明确终态及原因。保存所有实际 callbacks、truth、operations、已分配 attempts、raw 和失败；保留当前 201 IDs，不移动到新的 action 边界。原 teacher、120 settle、七动作加两次 dwell、controller 参数和既有 dynamics 不需调整。修复后重跑这一个 exact RED 与 owned CPU，并冻结新 source/header/manifest；不得覆盖本轮 quiet 输入或旧实际采集。

## 通过的限定核验

- 独立 source preflight 匹配 34 live/archive 来源、432133 bytes；31 个旧 source 引用原 archive，只有 prepare/runner/v4XML 三份新副本；21 个环境 pins 匹配。实际 module-only runtime 为 MuJoCo 3.3.7 / NumPy 2.5.3，public/binding class identity 与三个 binding origin 均匹配。来源 preflight、runtime preflight 在冻结执行器第一次 session/model/reset/camera 之前。仅在内存模拟 live helper、archive helper、guard、environment bytes 漂移与 /tmp frozen runner 漂移，五类均拒绝，没有更改实际文件。
- 原 offline markers 重新读取 4807 条，step 0..4806 与单一原 episode identity 一致：4618 OBSERVED、189 UNKNOWN。固定选择恰好全 189 UNKNOWN 加 12 个 OBSERVED controls，共 201；header 与 manifest 完全一致。九个原 input pins 与 201 个原 compressed frames SHA/bytes 已核对，不解压或重解码旧 RGBD。旧 pose 来源缺失 190 个 selected states，preview 为 UNAVAILABLE_MISSING_ORIGINAL_FULL_QPOS、render budget 0；未组合旧状态作反事实。
- v4 XML 的全部非 marker 树、body/joint topology 与 frozen v3 相同；ID7 色块图样不变，37 visual tiles 均 mass/density/contype/conaffinity=0，tag 75mm，local X 160mm，Z 不变。cube/camera/controller 来源保持原 pins。这里只证明源码/XML 结构，不声称 compiled-model 等价或可见性改善已测量。
- Fresh adapter 在实际 selected capture 前读取并验证 qpos37/qvel33/act0/ctrl9，附入 offline journal，不向 decoder 输入 truth；只委托一次原 camera capture。原 support-aware Data guard 与另外 11 个 protected components 保留。旧 decoder、注册表、thresholds 和 reviewed guard/V3 来源未改变；未重跑其 full90。
- 所有实际 physics callbacks 先计数；原 teacher 在每个 callback 前加入 physical_samples，原 nominal operation/actuator observers 与 action wrappers 保留。固定原配方代码仍为 120 settle、9 个动作，其中两个 dwell 是 0.5s 与 1.2s。只对固定 201 步额外 RGBD 采样，旧 setup/bootstrap/teacher boundary capture 仍单独计数，不能把它们充作全时域 visibility。
- 独立 sparse BEGIN/END/FAILED/PHYSICAL_CALLBACK publication CPU 控制均得到 INCOMPLETE，attempt/callback/failed 分母完整；END 发布失败已写出的 raw 保留，FAILED 发布失败保留原 camera 异常及 secondary note。owned inherited acquisition failure tests 亦通过。

## 命令与计数

| 检查 | 独立结果 |
| --- | --- |
| owned test_cpu.py，禁用 pytest cache，临时目录在 /tmp | exit 0，34 passed in 0.40s |
| Ruff check，仅 3 owned Python 文件 | exit 0 |
| 3 owned 文件 in-memory compile | exit 0 |
| Ruff format --check，同 3 文件 | exit 1：仅 prepare.py 两个等值相邻字符串会合并；样式观察，不是行为 veto |
| source/runtime/selection/XML narrow CPU controls | PASS，实际 engine 调用 0 |
| sparse publication failure narrow controls | PASS，4 场景，实际调用 0 |
| R01-V4-RANGE-01 exact CPU RED | expected exit 1，额外终点误标 COMPLETE |

作者 34 tests 与本次独立复跑的是同一集合，不能相加为 68；本次报告计原有 34、独立运行 34、新 qualified RED 1。临时 fixture controls 单列，不算作者新增 tests。未重复全 reader4807、旧 90CPU、guard suite、全 10GB 解码或实际执行。

## 保全与证据 pins

342 个固定 slice inputs 的 before/after SHA 全相等，changed_inputs=0；不扫描整个仓库。完整两个 SHA maps 和 command 输出见 JSON/log。只创建本轮三个 independent-review 文件。关键 quiet pins 如下（before=after）：

| 文件 | SHA256 |
| --- | --- |
| `prepare.py` | `924925f327972c0416e522eed11389d70ebb59320304995995204595c29dbe5f` |
| `run_sparse_once.py` | `41891f66660425677010343f0d50f6894d329dbfc898728a1973fb5666e2efad` |
| `test_cpu.py` | `b6383b1a4daf997d4e20c4a13f6d9052776fc0df50927c0e20d00e9c3a93c3f6` |
| `scene_pose_marker_outboard_v4.xml` | `045ce032032426ec6130348ee75e5f53b7db02699fc1f39558727edd63f67e0d` |
| `selection-manifest.json` | `0058c54bfb8d70709630ac65bf05fb8f11426b8325cc04848ed6aeece1678cb5` |
| `pilot-protocol/header.json` | `c1af095f5f0aa6ac3bff39bdc63ad5d3a0a4267b00e292f07b2c901a4fdc2867` |
| `pilot-protocol/execution-source-hashes.json` | `e6a3067c663097bf5d648748f521d6d4588664ae39a9c7b93e70d8b5e96a3d69` |
| `pilot-protocol/execution-archive-index.json` | `79ed7a247a035cbf58c41bc7ed33753eaf12ee73df05906ede8579f45cd7168e` |
| `report.md` | `657354472614bdf814225d583e5d66303d3256bb9f0ab0d85204260e777ff9db` |
| `report.json` | `2a98e53bbccc781f93117005ecbc9a723f1ed805ff8a6086faa5ab803916ffd3` |
| `owned-pins.json` | `43e96a5cc141f39425da35bf1381ed9faae0caa66ad8413099e297154be4e7da` |

review log SHA256: `403415868c7aae4b2c5447d71554f3216b21f7765edb831accd8ef1dd262eecf`。

Sparse、native/UTC/calibration/group/future/formal 均未提升。640/noise0 excluded development 仍不同于 formal 320/noise.001；37 visual attachment 无物理支架，visibility effectiveness 未测量，source authenticity UNKNOWN。REQUEST_FIX 只针对范围终态，本评审没有停止或否定实际 pipeline 已完成的旧 R01 局部结果。修复定向复审后，由 root 执行唯一 fresh attempt，无新用户许可流程。
