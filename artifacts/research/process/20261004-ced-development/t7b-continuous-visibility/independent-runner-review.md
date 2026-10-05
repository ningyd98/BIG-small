# 独立审核：逐物理步采集 runner / offline verifier

2026-10-05，初始结论：**REQUEST_FIX**。先取得作者 source quiet 确认，再做只读源审核、9 个 integration CPU 用例及小型合成轨迹反例。没有执行 `execute_once`、真实动作、MuJoCo renderer、模型或硬件；没有修改实现或既有 module review。

## 三个 qualified P2

1. **Journal 与已验证帧没有严格关联。** `verify_attempt` 验证 `ACQUISITION_END.saved` 中的时钟，却未把整条 saved 记录与 `whole-step/index.jsonl` 的对应 END 比较。只将 step 1 journal saved 中的 `observation_id`、`observation_checksum_sha256`、`file` 改成 unrelated 值，原始 index、gzip 和三个帧保持原样，仍返回 `VERIFIED`、3/3。这会把不同的帧声明作为已验证关联。应完整比较对应 END，并检查 acquisition、camera、physics 的 episode/step/sim-time 和捕获区间关系。
2. **终点 episode / simulation time 未绑定。** 独立将 `terminal.json.episode_id` 改成 `unrelated-episode`，或将 `final_sim_time_s` 改成 `9.0`，两个变体均仍 `VERIFIED`、3/3。现有检查只比较 terminal step 数与帧数。应把 terminal 身份和时间与 series、最后观测及最终物理源一致性连接起来，保留完整终点范围。
3. **完整 action span 可出现未所属帧。** 在已知 action `(0,2]` 内，将 step 1 的 ACQUISITION_BEGIN 和 END 的 `action_ordinal` 同时设为 `None`，仍 `VERIFIED`。当前逻辑只校验非空 ordinal，未从所有原始 span 推导每个物理步的唯一归属。应对整个实际 `(start_step,end_step]` 重建所属关系，拒绝遗漏、重叠或错误归属，不能缩短到有标签的子集。

基准合成轨迹首先通过；以上四个单独变体均 qualified，且均保留 `source_authenticity=UNKNOWN`、`formal_accepted=False`、`continuous_motion=NOT_CERTIFIED`。这些是离线关联完整性的缺陷，没有发生 native 权限提升。复现脚本不调用真实 runner；所有帧来自作者的小型 fake camera。

## 已完成的其余检查

- 独立运行新脚本内 **9 CPU cases，PASS，0.33 秒**；不重复已经审核的 17 个模块用例。日志：`independent-runner-tests.log`。
- 32 个 exact 输入、398,949 字节，全部 live / `source-before` / manifest digest 一致。原始 28 个输入没有更改；新增范围为最终模块、模块测试及这两个脚本。HEAD 仅为历史信息，源字节才是执行冻结条件。
- 同一相机对象、原配置、640×480 和原控制器；场景本来即零噪声。Adapter 在额外采集前拒绝非零噪声，并比较 data/model arrays、model options、controller、RNG、sensor cache 和 camera identity。CPU 用例覆盖这些状态突变、非零噪声，以及 backend 吞下的 observer failure。未用实际渲染来推断物理不变性。
- 逐步 hook 包括 step zero 和每个实际 mj_step，保留控制/actuator/physics/action/acquisition 来源。额外 RGB-D 是独立的 teacher nominal stream；setup 没有 observed RESET，因此明确不产生完整 native raw-v3。解码只在离线 verifier 请求时执行。
- 帧保持完整 `RGBDObservation` PNG、depth-f32、mask、calibration，经 gzip 后验证 byte lengths / hashes；原始 simulation gap 仍为 0.005。暂停采集消耗墙钟时间，不能当作 5 ms wall cadence。
- Journal 写入失败和 backend observer failure 将中止；StepRGBDRecorder 保留失败分母并禁止 retry。实际 attempt 使用固定 `attempt-1` 的新目录创建；已有目录阻止重复、覆盖或恢复。这个 guard 通过源审核确认，未尝试创建真实 attempt。
- Nominal clock brackets、external uncertainty UNAVAILABLE、UNKNOWN authenticity、NOT_PROMOTED、NOT_CERTIFIED 及 future/calibrated UNAVAILABLE 均保持关闭。CPU 成功或完整采集不提供连续未来运动界、native calibration、INITIAL 或 METHOD 接受。

## 保留的原始冻结与证据

| 项目 | SHA-256 |
| --- | --- |
| runner live / initial archive | `addc33e7031bdeb55d03a476b9d4c1ad97a789c43251ac1be79ff53c5596537a` |
| verifier live / initial archive | `bec19e9c8d2b7141299bfcdab462d28e786e0f97ee0d0a26a8ba624e706bb42a` |
| initial header | `da1a17c74414db46f26fdf5435d7e241b84cd70cdae9def7d66d69a911126795` |
| initial execution source manifest | `08bebf77fb36db8e521937ad5296b8e0471059b66a773633e6bccb6880fa6495` |
| original qualified CPU probe | `c4fc7b5a2e2fe80c8725b3b700481808522e11f2bff84bcdd935334bb611c40f` |
| original counterexample JSON | `5aae0ceaf276581cda58b3a11af8fdb0bdb2a0d43efe6e66bc64f7624cb5234f` |
| unchanged module review | `a7ae2306bd4fd8c04c4ad0fb2d620f9b58e8489bb11f462f91c77214e8bc0847` |

证据文件为 `independent-runner-probe.py`、`independent-runner-counterexamples.json` 和独立 CPU log。三项修复已交给作者；实际完整试验等待修复后的 quiet source 和独立复核。初始 REQUEST_FIX、反例、日志和冻结 hashes 将保留。
