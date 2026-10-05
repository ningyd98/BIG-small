R03 最终 P1–P4 与 root CLI 切片独立审查：`PASS_SCOPED_SOFTWARE`。

本结论仅针对冻结的 source-only RESET prefix 软件路径，支持 root 在当前审查 pins、默认正式 camera/noise/domain、唯一新输出目录和串行 renderer 条件下运行一次 excluded RESET/120 settle/freeze/A–B 诊断。该结论不授予 adopted RawV3、native/UTC、continuous、consumer feasibility、calibration group 或任务执行权限。独审 actual UDP、provider、model、renderer、native physics、decoder、calibration 调用均为 0。

已独立检查真实 startup → SQLite job/lease/唯一 open attempt → worker early source-only branch，原 RESET/RawV3 observer 顺序、A/B 整体冻结与 guarded publisher、失败原件保全，以及 CLI 默认无 actual 行为。审查不改实现、旧原件、rootdocs、Stage 或 Git；只新增本目录的 independent-review.md/json/log。

- 所有 issued application/worker/repository/capture/recorder/source/verifier 精确原对象受 private registry 绑定；复制的公共对象、其他 worker/repository、过期 lease、变更 job assignment、source/config/asset/binary/verifier 不提供该路径授权。源与租约检查先于 backend 创建/initialize，并在 exchange 与 publication 再读。单次分支先于 planner，prepare/execute 不允许内部重试。
- RESET 日志另起 journal 序列，tee 保留原 `_clock_pair()` 返回 tuple，仍调用原 sole RawV3 observer；BEGIN 保留旧 episode，END 保留新 episode，CONTROL/PRE-step 与 PHYSICS/POST-step 原顺序未改。worker diff 与保留原件重建完全一致，仅 3 个 bounded hunks。
- RESET/SETTLE 的 cached CAPTURE 是实际运行时真实 renderer 工作。软件测试只替换 renderer/RESET/step；未来 actual 的每次 cached frame、失败 allocation、operation/error 分母均保留。这里只能说 explicit acquisition、planner/model 与 action request 为 0，不能说 actual renderer 为 0。失败 cached capture 使 prefix incomplete；导出 frame 失败也不能掩盖。
- 原始全部 clock pairs/RESET callback/物理控制/frames/errors 先 freeze，再生成 B commitment 与 previous-A 原件。发布复用固定 R2 wire/causal verifier；A verified → 每个 frozen pair/RESET callback → B sent，仅给历史 slab enclosure。秒级 quantization、UNVERIFIED issuer 不变；B 后 now、native UTC、actual consumer feasibility 始终 UNAVAILABLE，TTL 比较仅历史宽度必要条件。未把 fixture 的 6 秒 enclosure 升级为默认 5 秒 TTL 或 metrological 精度。
- publisher 在真实 repository publication guard 内复验 ownership/lease/source 原件，完成 original/export/hash checks 和 catalog 写入后才暴露 private live catalog。原来的 real catalog-write failure case 已独立通过：raw/failure 原件保留、job BLOCKED_BY_ENV、没有 live catalog、无隐藏 retry。公共 offline reader 的 VERIFIED 只是原件 hash/RESET/raw join 一致性；独立 caller catalog 不铸造签名或 native authority。
- 健康 software prefix 可以 COMPLETE 且 SQLite job SUCCEEDED，即使 A 无可验证签名；该值仅表示 RESET/120 settle 原件路径完整，receipt 同时保留 raw source UNBOUND、native/current UTC UNAVAILABLE、task_execution NOT_RUN，不是 native 正授权。
- 真实默认 CLI 实测 INPUTS_ONLY / NOT_RUN，指定 /tmp 输出目录未创建；execute-once 独立 9 项 CPU case 包含 strict `prefix_complete is True`、原 receipt 保留、失败出口和无 retry。

独立验证执行一次，全部 exit 0：owned 31 项 CPU（11.92 秒）；指定 narrow 16 项回归（4.43 秒）；Ruff 8 文件；format 8 文件；mypy 3 source files。作者 quiet 31 与独立 31 是同一 owned 测试集合的两次观察，不能相加为 62；16 项另列。owned fixture 使用真实 SQLite/observer API，backend RESET/physics/camera/network 为 SOFTWARE_ONLY 替代；其中 pinned Go request/reject CPU case 使用真实固定 binary、替代 UDP 响应，没有实际 packet。未重复 Go build、旧大审计或全仓测试。命令、完整 stdout/stderr 和 SHA 表见独审 log/json。

冻结的 105 项本切片输入、86 项提供的期待 pins 全部匹配，审查前后 SHA 与 bytes 相同（changed=0）。未新增 qualified RED，未发现需修复的当前实际软件缺陷。`source-hashes.json.cli_slice_report` 无 path 字段，按 root handoff、1334 bytes/SHA 以及 CLI report.json 内 report_sha256 正确对应 cli-slice/report.md；CLI JSON 本身也单独冻结并一致，没有 hash drift。审查 harness 的两个准备期断言在 /tmp 修正后才启动一次验证，不计为 implementation RED。

关键 quiet pins（before=after）：

- RESET recorder：`a22ce81503a1dd7d6aa9b81a57eb61cebcbda64ec58228a5c4dbe21da1e41f5a`
- publisher：`3eed8c44c4bb0657741a3f9ab113f9f035b3d73d5aa8ed8ca4c5c24fca880105`
- worker：`e1facb79224d58e92b3e48a00806c32468a45174742b280575304a3d8036b008`
- CLI：`c9630134e1fa0039dfb040bbf92e1e0401d175efe34e0c46939ec47de22ada83`
- source manifest：`97643ac966903e4181e58a36c8b0775a22000a6286f999cd9cbee3ac16ebd35f`
- fixed Go binary：`930095fe5f13ab9522691fbedba1273f56a6a9f27823038093f4b99de7b6d313`；official upstream commit `75645289794cfbd71a08f0e7ecf9bc4f3f87d133`，metadata `a68ce1ae89535d6f779092d712fae858d514ed22402dcc8b6903bda5c2363fef`。

独审 log SHA：`45a3e0bca173e418208c3d626255b3ba41e02f3ac048d9c0ac914b9e15ecb692`。完整 before/after inputs 与命令见 independent-review.json。输出完成后停止写入。
