# R457 OpenAI Sol 云端迁移 Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans 由 ROOT 内联实施；本轮只规划，不另开设计审批。

**Goal:** 云端RGB-D角色按用户指定精确使用 `gpt-6.1-sol` 和OpenAI官方API，保留历史Qwen兼容及本地密钥边界。

**Architecture:** 维持现图像+JSON Chat Completions。将Sol有效参数和地址校核集中到已有model_resolver，角色/active adapter/请求构造/probe采用同一参数定义；probe和pilot显式校核配置家族。无新模型选择、prompt改写、Responses迁移或真实校准流程。

**Tech Stack:** Python现有urllib、不可变dataclass快照、SecretStore、pytest软件边界。

**Spec:** ROOT转述的用户新要求及 `intake/verified-official-facts.json`。实际规划模型gpt-6-astra；HEAD只读确认为 `c96289351b3e60f8ac183c8f331fbce484ad7340`。23份输入完整副本/SHA见intake，静态不兼容片段已保存。没有执行失败测试或实际API证据。

## 全局边界与官方依据

官方事实已由ROOT核验并提供，本规划不重复联网：[精确模型](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[迁移指南](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.1-sol)、[Chat创建参数](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。当前不使用tool calling，故可保留Chat。reasoning支持low/medium/high/xhigh/max，不支持none；选择low延续原think=False的低推理投入意图，但不称其等价。非none时省略temperature/top_p/top_logprobs/logprobs；max_completion_tokens含推理tokens；保留JSON object响应。

本轮不读取环境密钥、不接收或复制聊天密钥、不访问现运行DB、不自动创建/激活profile、不修改现Qwen profile。所有测试用临时DB和虚构测试secret，外部HTTP仅替换边界；无真实API、MuJoCo/render、GPU服务或硬件调用。两脏gitlink不动。正式研究始终NOT_ACCEPTED。

## 静态根因及精确范围

现ced_roles/read_role_config锁Qwen；select_cloud_model_id只有Qwen正则；role生成temperature/num_predict/think；ModelConfigSnapshot不允许字符串effort；planner发送temperature/max_tokens/enable_thinking；active service.visual_planner固定512；probe summary与expected body仍按旧字段；probe/pilot尚未校核role_config家族和profile一致。这是同一“云端模型能力与请求来源绑定不匹配”根因，一轮收敛。

允许修改六个代码文件：vision/model_resolver.py、role_models.py、planner.py，model_control/service.py，scripts/probe_rgbd_roles.py、run_rgbd_pilot.py；配置configs/research/ced_roles.yaml；当前入口docs/research/reproduction.md；新增tests/test_openai_sol_visual_migration.py。完整路径见plan.json。旧model_control通用文本planner、endpoint_security、SecretStore、schema/DB/UI、frozen_model、probe_rgbd_model、历史fixtures及其他研究源码只读。尤其不把旧Qwen fixture整体换为Sol。新增helper放在已被source_fingerprints覆盖的model_resolver，避免扩展源码闭包。

## Review Focus（由下列八节点覆盖）

- 配置Sol但选旧Qwen profile，必须在renderer/HTTP前拒绝。
- 官方host但错误拼接/v1重复、URL凭据/查询/重定向，不能把secret送往其他地址。
- snapshot允许的参数与实际发送字段不同，必须被hash/summary证据发现。
- active profile或environment仍512/旧frozen优先，配置说明与实际请求必须一致。
- 软件wire成功或截断JSON不能转成云模型可用/本体/full-H/native资格。

## Task 1：写一次软件 RED（新增8节点）

- [ ] 复核所有输入SHA，建立新R457 runner、before和命令记录；不导入secret环境或现DB。每个新节点先断言 `callable(getattr(model_resolver, "sol_generation_parameters", None))`，消息统一 `R457 Sol request policy missing`。旧模块可正常导入，避免import错误冒充RED。
- [ ] 八节点及最终行为：

1. `test_sol_snapshot_strict_generation_and_hash`：精确Sol snapshot接受 `{reasoning_effort:low,max_completion_tokens:4096}`；五个合法effort逐项验证且改变digest；none/任意字符串/bool effort拒绝；token bool/float/非正/超上限拒绝；Sol多余legacy参数拒绝；其他模型不能借新增字符串键逃过旧验证。
2. `test_sol_official_route_and_paid_guard_before_transport`：仅两种准确base/path组合通过；http、lookalike/subdomain、端口、userinfo、query/fragment、任意路径和/v1重复拒绝；provider错或Sol snapshot/model可变字段漂移拒绝；allow_paid=False在外部HTTP前停止。Sol请求不跟随redirect，直接调用专用redirect handler软件边界证明无跳转，不启本地HTTP服务。
3. `test_sol_role_family_profile_and_entry_binding`：当前config选Sol且profile_id仍null；新临时Sol profile通过、Qwen含合法dated家族保留；Sol不自动选registry别名/日期型号。expected_model_family与profile不符直接拒绝，不取secret/不激活。用禁止renderer/transport边界覆盖probe与pilot向resolver传入family的实际入口；pilot原probe前置可用既有软件fixture供给，不能因此宣称真实probe。无family参数的历史直接resolver调用保留兼容。
4. `test_sol_two_image_json_wire_and_grounding`：实际RGBDAdapter→_post序列化，外部opener返回软件JSON；真正构造RGB和depth两张不同inline PNG、JSON response_format、exact model、low及4096预算，保留normalized_1000→原像素grounding和无truth消息。断言请求JSON没有所有不支持键；不mock _request_visual或消息构造。
5. `test_sol_active_and_environment_effective_budget`：临时active Sol的visual_planner采用profile.max_tokens（例如8192）而非512；不可变snapshot不随profile更新改变；Sol环境fallback为low/4096，base/v1与默认/chat路径拼成官方地址。测试用monkeypatch清除/设置dummy环境；验证已有FROZEN_DIR优先规则保持，使用旧freeze时不能声称已切Sol。禁止读取用户真实环境值。
6. `test_sol_probe_summary_and_source_drift_binding`：actual wire summary含reasoning_effort/max_completion_tokens，与预期body及snapshot一致；变effort/token/model/path/provider改变绑定或提前拒绝，source_fingerprints确实包含model_resolver；两种支持URL分别被如实绑定。覆盖实际probe _attempt expected-body分支的软件帧及fake transport，不能仅测试手拼字典；status不获研究接受。
7. `test_sol_rejects_truncated_response_without_authority`：fake HTTP返回finish_reason=length且内容截断/无有效JSON，现严格解析失败、计账有真实软件边界字节、不会自动重试/增预算/产出可派发合同或freeze。
8. `test_sol_qwen_and_secret_boundary_compatibility`：Qwen原temperature/max_tokens/enable_thinking行为不变、Ollama原think/options不变；测试secret只在既有Authorization边界，快照/summary/report不含secret，echo抑制仍有效；缺secret/不付费入口拒绝。仅临时测试身份，不触真实SecretStore。

- [ ] 执行唯一sol-red，预期恰8个上述缺helper AssertionError失败。任何其他失败暂停，不补跑。

## Task 2：有效参数、路由、来源绑定

- [ ] 在model_resolver新增小型纯helper：

`sol_generation_parameters(max_completion_tokens: int=4096, reasoning_effort: str="low") -> dict[str,int|str]`：严格枚举；token必须精确int且1..32768（项目本轮预算上限，不声称供应商最大值）。

`validate_sol_route(provider: str, model: str, base_url: str, chat_path: str) -> None`：Sol必须openai_compatible，允许且仅允许 `https://api.openai.com` + `/v1/chat/completions` 或 `https://api.openai.com/v1` + `/chat/completions`。在原endpoint规范化后做精确组合比较；不允许credential/query/fragment/显式端口/另一个host。不得把urljoin的任意绝对path绕过它。

`compatible_chat_generation(model: str, generation: Mapping[str,int|float|bool|str]) -> dict[str,object]`：Sol返回经过严格验证的两个有效wire字段；非Sol保留旧temperature(default0)/max_tokens(num_predict default512)/可选enable_thinking映射，不新增legacy请求键。

- [ ] ModelConfigSnapshot.generation_parameters精确扩展字符串类型，但字符串只允许Sol reasoning_effort。Sol配置必须恰reasoning_effort+max_completion_tokens，拒绝不匹配provider、legacy参数、缺失/多余字段；原非Sol验证/证据形状保持。Sol endpoint在snapshot验证base，再在adapter已知path时完整验证。所有证据保存有效参数而非profile的未发送temperature；无模型权重/版本证据时继续null。
- [ ] role resolver只新增exact Sol分支，旧Qwen family及真实advertised dated选择保持。新增keyword `expected_model_family: str|None=None`，配置给Sol要求精确Sol，配置给Qwen要求Qwen家族；None保留历史直接调用兼容。family校验在读取secret/建transport之前；不得自动切换profile。Sol generation=low/profile.max_tokens；Qwen原生成参数不变。
- [ ] RGBDPlannerAdapter compatible请求用同一helper；Sol无snapshot的环境/直接交互路径默认low/4096（仍不是研究冻结snapshot）。构造和wire前都校核Sol官方路由；若snapshot是Sol而mutable model/provider改走其他值，须在HTTP前拒绝，不靠换model绕过。_post只对Sol添加不跟随重定向的handler；非Sol opener/endpoint策略不变。现支付门、secret边界、HTTP observer/成本字节/解析/失败语义保持。对Sol请求不发temperature/top_p/top_logprobs/logprobs/max_tokens/enable_thinking/think/num_predict/num_ctx。
- [ ] service.visual_planner仅Sol分支用profile.max_tokens与low，避免固定512；其余provider原参数保持。不要顺便改通用文本planner、profile CRUD/schema、数据库或自动active逻辑。
- [ ] read_role_config允许两个明确家族，当前ced_roles.yaml只将model_family改为exact Sol及相关当前注释；320x240、normalized_1000、grasp、device/edge policy/source列表保持。run_probe和run_rgbd_pilot实际入口均把配置family传给resolver；历史验证器validate_role_probe_bindings不额外加新family条件，以免旧Qwen内存报告借当前配置路径突然失效。
- [ ] probe summarize_role_request对Sol记录真实reasoning_effort/max_completion_tokens；legacy summary形状保持。_attempt预期请求用同一纯helper构造，不再硬索引temperature/num_predict；actual仍从收到的raw请求计算，不能复用expected冒充actual。Sol snapshot里的generation原样进入cloud_request_settings/request_config_hash；不向所有provider增加新effective字段。保留原wire SHA/count/双图/hash/来源与secret echo拒绝。无需修改source_fingerprints路径集合，已覆盖所有helper实现；新增测试断言此闭包。

## Task 3：当前说明与一次验证

- [ ] docs/research/reproduction.md当前“Max配置/新Max探针”说明改为用户指定Sol，并加2026-11-08变更说明：旧Qwen证据按原日期和源码保存，不重写历史结论。给出非敏感新profile示例：provider OPENAI_COMPATIBLE、model gpt-6.1-sol、base https://api.openai.com、path /v1/chat/completions、max_tokens4096、timeout180；说明此字段在Sol映射max_completion_tokens且含reasoning，low默认。profile配置不是可用性或图像能力验证，不自动create/activate。
- [ ] 密钥由用户本地配置，推荐在其本地会话/secret管理中设置OPENAI_API_KEY；probe可用现 `--secret-env OPENAI_API_KEY`，默认仍BIGSMALL_VLM_API_KEY，无SecretStore改造。Web UI SecretStore为session内存，重启不等于持久可用。文档不放密钥值、不要求粘贴到聊天、不读取现环境。一般环境交互路径使用BIGSMALL_VLM_PROVIDER=openai_compatible、MODEL=gpt-6.1-sol、BASE_URL=https://api.openai.com/v1；密钥仍走既有BIGSMALL_VLM_API_KEY变量，显式说明它与CLI的--secret-env不同，不自动跨变量复制。
- [ ] 明确from_environment已有FROZEN_DIR优先；.env.example旧有效frozen设置必须在用户选择Sol环境路径时unset，否则仍加载旧冻结模型。本轮不改该文件或关闭用户当前freeze，不自动设置ALLOW_PAID。真实probe的--execute会启动renderer+HTTP，本轮不可执行；不给可直接触发实际调用的“一键验证”指令。
- [ ] 单次格式化六代码文件及新测试（只批准路径）；随后唯一sol-green8PASS、adjacent-green清单全部PASS、ruff/format/mypy各一次。详细argv/env/新basetemp/JUnit/events在spec-templates和plan.json。相邻只跑rgbd_role_models、rgbd_normalized_protocol、ced_pilot_stages、active snapshot节点与model-control两个纯secret/endpoint节点；不跑全套/真实engine节点/现R439流水。旧测试只读，若出现原fixture不兼容按证据暂停交Astra，不能替换全部Qwen文本。

各stage串行attempt1，sol-red/green child180s outer300s，相邻child240s outer360s，静态child120s outer240s；所有真实API/physics/render/model/GPU服务/硬件计数0。旧非本轮静态问题如出现要单列，不以Any/ignore或大范围修复吞掉。所有原日志保留，异常失败按AGENTS新Astra，不无意义重跑已通过集合。

保存每阶段result/stdout/JUnit/events、实施diff/前后pins和step-report；做针对迁移整条绑定链的只读复核，不重审无关物理模块。软件通过仅说明兼容构造与拒绝行为，实际账户模型权限/响应/延迟/费用/双图能力均未验证。

## 旧研究协议失效与后续真实前置

模型配置及源码改动使旧R439 source-generation/protocol不能用于新源码实际运行。保留其冻结字节和全部历史软件/失败原件，只在本轮报告/当前说明标注“新模型与源码需新source generation”；本轮不重跑prepare/full/read、不改旧协议、不授予九组/实际额度。后续真实运行须另有当前源码冻结、用户本地secret、明确付费/调用预算和真实探针/独立校准前置；R450 GPU服务授权独立。当前正式研究NOT_ACCEPTED，native及远端不可观测版本继续UNKNOWN/null。

自审：精确模型与用户方案不替换；参数快照/wire/summary同源且actual独立读取；legacy形状保留；两actual入口family闭合；密钥不参与计划；单轮小范围软件交付；无真实调用授权。
