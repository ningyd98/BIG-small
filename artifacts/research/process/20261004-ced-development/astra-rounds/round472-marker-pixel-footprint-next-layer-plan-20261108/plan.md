# R472 marker像素占幅：下一层静态方案计划

实际规划者 `gpt-6-astra`；NEXT_LAYER_PLAN_ONLY_NOT_EXECUTED。本轮只写计划，后续可执行一次限定stdlib静态分析；不修改产品/资产，不调用detector/engine，不授权第三次actual。历史真实attempt仍2。

## 证据与判断

R471四份原图生产detector均known_marker_not_observed；同灰图idsNone、每帧4个rejected。固定显示crop中唯一候选bbox(194,116)–(202,123)，边8/7/8/7px。它没有解码ID，不能当marker truth；即使这些角点能解码，min7仍达不到现有min8，不能靠简单放宽或上采样冒充原生分辨率。XML36bits/位置序与ID7一致，合成control解码7，排除了静态位图错码及decoder不可用；实际sampling/rasterization/contrast根因和修复仍未证实。放大几何可能增加名义占幅，但不能据此宣称能解码或通过depth/pose/遮挡检查。

HEAD `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`，source_generation `e5795af5d1a7b90a7dcb442da0f37c0ec9fe4fad04d13e3696c4a5cf609fdd55`，423项源码/固定输入与16项新证据SHA见plan.json。R471实际receipt路径从step-report.execution_receipt解析为implementation/delivery/offline-execution，提供的省略implementation路径只读查找曾FileNotFoundError，已记录，不影响原实验。

## 一次有限静态分析

ROOT只实现本轮analyze_footprint.py并做AST/JSON/hash核查后冻结。

1. 重验输入/source；直接复用R471数值，不重复detector。
2. 纯XML/protocol解析camera、marker/quiet矩形和名义初始位姿，pinhole计算一个固定名义姿态下的side/cell/quiet footprint，明确NOMINAL_STATIC_PROJECTION，不称真实可见性。
3. 只比较三个内边长0.045m基线、0.060m候选A、0.075m候选B；同marker中心/朝向、quiet比例4/3。计算名义投影及物体/图像边界间隔；这些是未选定的设计假设，不创建资产或扫参。原7px候选只作背景，不充当已校准缩放定律。
4. 明列更大占幅对red-rim/物体颜色、目标区、机器人遮挡、corner depth patch、registration、旋转及全horizon可见性的风险。只否决可静态证明冲突；其余CONDITIONAL，禁止OBSERVED/PASS。
5. 提交独立版本asset/registration建议与精确当前consumer/hard-hash/source_inventory依赖图。旧v3、graspv2、协议/原raw/hash不变；本轮不创建XML/config、不改固定策略或做通用化重构。
6. 给基线/A/B已知与未决条件及最小下一证据建议；若不足，实际Astra另轮冻结有限诊断或明确授权的渲染验证。现在不执行也不释放quota。

保持marker7、顶视camera的pose/FOV/resolution、controller、OpenCV、graspv2；不调threshold/errorCorrectionRate，不使用instance/physics truth填visibility。_Audit.domain独立deferred，不混入。

## 精确后续命令

```sh
/usr/bin/timeout --signal=TERM --kill-after=5s 90s '/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python' '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round472-marker-pixel-footprint-next-layer-plan-20261108/implementation/analyze_footprint.py' --plan '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round472-marker-pixel-footprint-next-layer-plan-20261108/plan.json' --output '/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round472-marker-pixel-footprint-next-layer-plan-20261108/analysis'
```

cwd为仓库；env见plan.json，stdlib only，无product/cv2/numpy/Pillow/network导入。wall60s/outer90s、RSS256MiB、输出32MiB、一次/retry0。ROOT捕获原stdout/stderr/rc/时钟与SHA，source前后不变。任何新异常先保全、下一Astra，不自动rerun。输出footprint-options.json、versioned-asset-design.md、dependency-map.json及source-before-after。

## 未来修复与actual门槛

诊断/设计review后，另轮Astra才能决定新asset/registration具体版本与路径及最小源码变化。旧v3/hardhash/raw不改，维持旧世代reader。需要必要软件RED→GREEN：版本/geometry/hash错配先拒绝；新版精确位图/尺寸/transform/source绑定，旧版兼容与foreign/ambiguous/undersampled负例保持；原低分辨率不能靠放大数据变GREEN。静态zero-mass/no-contact不能替代引擎物理等价验证；任何使用renderer的验证都算另行冻结的实际工作，不借“测试”名称绕过预算。

任何未来src/config/asset修改使待执行R469 P1来源冻结失效，须暂停并由实际Astra重新冻结新source/命令与fresh binding，不向旧protocol重贴hash。本轮source不变，P1仍受自身pins/前置条件约束。

本阶段交付真实partial与R471离线证据及本下一层计划，native UNKNOWN/formal NOT_ACCEPTED。reviewable诊断/修复完成后再另行确认第三次actual的精确边界；不得借旧retry0扩张。raw/DB本地保留，显式路径提交推送已验证process artifact并核对本地/上游/远端SHA。
