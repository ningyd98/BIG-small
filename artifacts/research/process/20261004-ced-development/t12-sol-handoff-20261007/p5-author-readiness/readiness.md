# P5 只读作者准备报告

状态：READ_ONLY_READINESS_COMPLETE_NEEDS_ASTRA_SCOPE_PLAN。只读派单已完成；尚未实施 P5，不声称软件或独审通过。

已复核 7 个现存 owned 源的字节数/SHA256、2 个 NEW 路径仍不存在、brief 与 Sol 总计划哈希，全部匹配。产品源码保持静止；本轮仅写此文件及 readiness.json。

## 真正启动入口的范围缺口

Ordinary actual worker startup creates the real lease/open attempt and original task origin, but does not issue a P5 private startup capability or retain an OC1 original task receipt. Public WorkerRuntimeSource carries identities, hashes, UTC origin and finite timeout, not an actual worker/private issuer. Runtime construction occurs after backend initialization/reset/120-step settle.

OperationalWindowOwner.from_worker cannot authenticate the current actual startup or reconstruct the original operational deadline solely in the nine owned paths. Opening D at the later public runtime constructor would grant authority from a public input and refresh the original task budget; float monotonic/UTC values cannot be converted to true D authority.

No workaround implemented. ROOT must commission actual Astra R100 for the minimal genuine worker startup issuance/handoff/lifecycle extension and then dispatch implementation. Existing P4 prefix registry is bound to its own exact live worker/job/origin/lease/attempt; an ended prefix grants nothing to P5.

ROOT 已确认将交实际 Astra R100；本作者尚未读取或收到该轮实施授权。NEW 窗口模块/测试及窗口描述、注册、局部事件分派属于原 Task5 预期新增；worker.py 的真实 startup 接入不在原九路径中，是需要限定扩范围的根因。P6 持久事务与执行闭包仍归 Task6。

## 九路径映射

| 路径 | 当前入口 | 原 Task5 预期工作 |
| --- | --- | --- |
| `src/cloud_edge_robot_arm/vision/operational_windows.py` (NEW) | absent, expected Task5 | OperationalWindowOwner.from_worker/issue/check/export_record; private live registry, independent OC1 owner, immutable event/budget/parents and boot/source/job/lease/attempt/fencing descriptors. Genuine worker startup issuance depends on R100. |
| `src/cloud_edge_robot_arm/vision/worker_runtime.py` (MODIFY) | WorkerRuntimeSource:110; VisualWorkerRuntime:243; _read_lease:316; check_active:411; reserve_capture:924/complete_capture:943; reserve_plan:981/complete_plan:989; supervision:650-860; grounding:1128-1166 | Bind genuine startup owner, acquisition/send/return/current receipts at existing private reservation/consume boundaries. Preserve original task/verification UTC deadlines, source validation and consume ordering. |
| `src/cloud_edge_robot_arm/vision/supervision.py` (MODIFY) | SupervisionContext:14; decide_supervision:52 | Local registered frame/plan window branch with exact context; preserve UTC reply identity and legacy branch. |
| `src/cloud_edge_robot_arm/vision/marker_association.py` (MODIFY) | MarkerFrameContext:272; factory:299; _associate:377, freshness:446; associate_marker_target:613 | Original acquisition window and observation/source binding; preserve freshness threshold and development replay distinction. |
| `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py` (MODIFY) | BootstrapDefinition:170, deadlines:224-236; _proposal_usable:523; _derive:588; capture:665, plan:696, retry budget:867 | Persist descriptive window/event references, dispatch supported local domain, clamp original task/verification/lease. Never relabel external nonempty UTC envelope. |
| `src/cloud_edge_robot_arm/repositories/event_autonomy/visual_supervision.py` (MODIFY) | SupervisionDefinition:97, deadline:226; _apply:519; reserve:558; capture:616; supervisor reserve:665; plan:675/late TTL:687 | Registered local capture/send/return references and unchanged original effective deadline; exact current context and lease guards retained. P6 remains transaction/execution closure. |
| `src/cloud_edge_robot_arm/edge/evidence/models.py` (MODIFY) | VisualEvidence:24; ActionEvidenceContract:39; EvidenceVerdict:71; DecisionEnvelope:83; CommitContext:104 | Descriptive registered schema/IDs; retain UTC fields and VALID/INVALID/UNKNOWN; data does not mint live authority. |
| `src/cloud_edge_robot_arm/edge/evidence/conditions.py` (MODIFY) | OnlineEvidenceSnapshot:38; evaluate_conditions:93; _evaluate:114; captured_at/age:127-137 | Supported local owner/window route; unchanged external UTC/third-party route, unsupported bridge UNKNOWN; caller-now or finite scalar not operational authority. |
| `tests/test_operational_windows.py` (NEW) | absent, expected Task5 | Named CPU raw-read seam cases only after authorized implementation dispatch; no test was created or run here. |

## 可复用 API 与权限边界

- `src/cloud_edge_robot_arm/research/operational_time_v1.py`：OperationalClockOwner.begin_event/mark_event/end_event/read_current (312-353)。Exact issued event/current pair and causal order; independent owner per applicable current startup, no caller counter.
- `src/cloud_edge_robot_arm/research/operational_time_v1.py`：within_age/start_deadline/before_deadline (375-424)。Age upper <= 5_000_000_000 ns; original origin/budget immutable; current upper < deadline, equality rejected. Boot/process/thread/namespace checks remain.
- `src/cloud_edge_robot_arm/vision/worker_owner.py`：read_visual_worker_lease (129-214), WorkerLeaseObservation (69)。Concrete repository, current RUNNING/cancellation, real lease expiry, exactly one live lease/open attempt, matching job/run/worker/lease/attempt. Observation/digest is evidence, not authority; no caller-now at live boundary.
- `src/cloud_edge_robot_arm/vision/worker_runtime.py`：_read_lease/_lease_key/_validate_role_sources/_validate_job_configuration and private claim/consume methods。Reuse identity and immutable source/config guards, real observation/publication boundaries; do not grant permission from public runtime source.

保留 ordinary/condition 5 秒、deadline 等值拒绝、原 task/verification/lease/retry/no-progress 预算。所有本地窗口必须指向真实原事件，不从回复、缓存读取或重观测重起 TTL；原 UTC 外部语义不变，缺桥接 UNKNOWN。source/hash/public bool/有限 scalar/导出描述都不签发 live 权限。R91 native 合同不扩窗口权限。

## 后续顺序（提议，未执行）

1. Wait for actual Astra R100 limited scope plan, input applicability and ROOT explicit Task5 product implementation dispatch; current authorization is read-only only.
2. Save authorized owned source-before and full local diff; write approved named RED using existing CPU raw-read seam, then one authorized run with original failure preservation.
3. Implement true startup-issued independent OC1 owner/original origin and lifecycle handoff under approved extension; real live lease/unique attempt/fencing/source checks must precede window authority.
4. Implement private registry/schema and immutable origin/parents/clamps for bootstrap/plan/grounding/supervision/marker/condition; cached frame retains original acquisition receipt and late reply/retry does not refresh budgets.
5. Connect exact local event boundaries and supported schema dispatch; keep nonempty external UTC, third-party lease/certificate/remote images strict UTC; unsupported bridge UNKNOWN.
6. Run only future dispatched owned GREEN/static budgets, stop any unexpected failure for actual Astra. Freeze source and evidence for different-author review; actual closure waits required P4/P6 and separate ROOT dispatch.

## 命名 CPU 用例（提议，未创建或运行）

- `test_five_seconds_inclusive_and_plus_one_ns_rejected`
- `test_deadline_equality_rejected`
- `test_missing_pair_foreign_domain_and_copied_handle_rejected`
- `test_valid_overlap_accepted_future_and_out_of_order_rejected`
- `test_reply_reobserve_and_new_event_do_not_refresh_origin`
- `test_cached_frame_preserves_original_acquisition_window`
- `test_external_utc_deadline_cannot_be_relabelled_operational`
- `test_utc_jump_is_diagnostic_only_for_supported_local_domain`
- `test_source_and_budget_changes_invalidate_window`
- `test_public_worker_or_source_without_startup_capability_cannot_issue`
- `test_ended_prefix_owner_or_lease_cannot_authorize_new_attempt`
- `test_closed_owner_or_changed_live_lease_attempt_fencing_rejected`

其中 reply_reobserve、external_utc、utc_jump 三个名称来自原 Task5；其余名称是将原边界及启动能力门映射为可审查用例的提议，最终以 R100/ROOT 正式派单为准。

## 精确证据

readiness.json 内保存本轮输入 pins、全部七源匹配记录及下列精确片段（行号、原文、文件 bytes/SHA256）。未复制全历史证据。

- `src/cloud_edge_robot_arm/simulation_runtime/worker.py`：80239 bytes，SHA256 `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4`。
  片段 128-136：only existing public/diagnostic task origin and prefix field。
  片段 166-193：actual lease cleanup and guarded unique attempt startup。
  片段 211-215：original task origin established before _run。
  片段 769-773：normal OpenCV origin guard。
  片段 824-839：public WorkerRuntimeSource construction。
  片段 878-914：runtime creation after reset/120-step settle。
- `src/cloud_edge_robot_arm/vision/worker_runtime.py`：62580 bytes，SHA256 `84ea21214453537e0c0d39ebf2da1a8ea3aa8539354089318e6d6398181fdfa1`。
  片段 110-124：public source fields; no private worker startup authority。
  片段 243-274：public runtime constructor。
- `src/cloud_edge_robot_arm/research/operational_time_v1.py`：20734 bytes，SHA256 `b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b`。
  片段 354-424：OC1 exact paired age, immutable origin, strict deadline。
  片段 526-536：production factory grants only OC1 counting。
- `src/cloud_edge_robot_arm/research/operational_prefix_v1.py`：65004 bytes，SHA256 `fbe8ee8f11911d3caaad32f91aacb30c927ccdf2018bc5913819a05afdc6348f`。
  片段 238-288：P4-only private token/startup/registry。
  片段 363-408：P4 exact live worker origin/lease/attempt checks。
- `src/cloud_edge_robot_arm/vision/worker_owner.py`：23511 bytes，SHA256 `ffce1cedb2cc9962ade0c5845d6ce92127372fa2248c0f4bc5f215706f5be86b`。
  片段 129-214：reusable real lease plus unique open-attempt observation。

## 执行边界与未满足门

测试/静态/产品导入/产品写入/actual/模型/网络/渲染/Git/子代理均为 0。没有借用已结束 P4 owner/lease，没有用 caller-now 或公开 runtime_source 自授权限。当前只读准备终态；等待实际 Astra 范围计划与 ROOT 明确实施派单。实际闭包仍需 P4 来源及 P6 门，软件准备不替代真实证据。
