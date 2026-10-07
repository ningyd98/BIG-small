# R06 当前 Max startup 读物勘误

本文件仅纠正原次只读复核的措辞，没有重新审计环境或配置，也没有产生模型请求。cloud、edge、device是三个架构角色；cold+3warm为四次名义请求。

原始[报告](report.md) SHA256：`876b537f0f44591742c8233db9f1aa5933b53f5d7cbe46055a603bb3f7d8bec1`。原始[机器证据](report.json) SHA256：`313d65c53d479d0b862758a63e35778a37127fe98002a6083cba7b3fed4d6c2c`。原文件保留；首段将“四角色请求”更正为“四次角色 probe 请求”。

## 原次复核正文（仅首段措辞勘误）

# R06 当前 Max startup 只读复核

本次重新读取当前环境和既有应用配置，不能启动新 Max 四次角色 probe 请求：`BIGSMALL_VLM_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`、`MAX_PROFILE_ID`、`MODEL_CONTROL_DB` presence 均为 false，项目 `.env` 不存在。默认 `data/model_control.db` 为 0 profiles、无 active；`dashboard/data/model_control.db` 为 10 profiles（5 个 rule-based、5 个 safe-model），纯 endpoint host 为 `api.example.test`，enabled compatible Max 为 0。两 DB 无非空 WAL，严格只读查询前后 SHA256 未变。

`ced_roles.yaml` 的已登记角色结构/元数据齐全：云目标 `qwen3.8-max`、320×240 双图、pixel、grasp v2、S01/seed0、cold+3warm=4；cloud.profile_id=null、available_model_ids=[]。日期快照/账户可用型号未知，不猜测、不联网。边缘规则原配置保留，型号后置、0 下载；端侧当前 OpenCV 来源保留。配置齐全不等于当前可启动或角色验收。

当前缺口有明确位置：默认应用 DB（或显式 MODEL_CONTROL_DB）内缺 enabled OPENAI_COMPATIBLE Max profile/真实账户 endpoint/约束；CLI --profile-id 或 cloud.profile_id 缺真实选择；显式 --secret-env（原 R6 为 BIGSMALL_VLM_API_KEY）缺当前 secret；目标 profile 不存在，因此当前 max_tokens/timeout/预算未冻结。没有恢复、创建、激活 profile 或修改环境。无需重复询问用户旧配置问题，交由 root 按原 Astra R6 继续其受控配置工作。

现存 startup 工具只有角色探针，默认会创建目录并写 report；--execute 会构造可初始化 DB 的 repository，随后才发请求/启动 renderer。因此本次仅静态读，未执行它。旧两份实际 CLI 输出仍为 NOT_STARTED / bundle=false / attempts=0；当前无请求只读结果见 report.json 的 existing_startup_preflight.current_actual_readonly_output。历史 35 calls 仅分类为历史，不与当前 0 calls 相加，不能恢复当前 profile 或 secret。

只有当前环境 presence 与已知 DB 公共字段被检查，应用 InMemorySecretStore 为 SESSION_ONLY；没有读取进程内存、外部账户或全 home，不声称所有 app 全局都无密钥。公开报告只保留布尔、模型 ID、纯 host 和文件 SHA，不包含 credential 值或认证 URL。

本轮 0 model/network/renderer/physics/test/download、无源码/配置/DB/Git 修改；只新增本目录 report.md/report.json。固定输入 SHA256、DB 只读前后验证以及原 Astra R6 边界写入 JSON。本次只复核原已知前置缺口，不实施修复；如有新的根因或范围扩大，由 root 先取得新 Astra 计划。

主线保持 T12/18，T13 并行，边缘选型后置；本局部前置缺口不将全研发标为 blocked。四次真实 probe 未执行，正式研究验收仍 false。
