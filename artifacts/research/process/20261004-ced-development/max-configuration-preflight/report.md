# 云端 Max 配置只读预检

结论：当前项目可定位的实际应用配置不能直接启动新的 Max 角色探测。默认 `data/model_control.db` 存在，但 profile 为 0、active 为空；`dashboard/data/model_control.db` 的 10 条记录全部是 E2E 测试配置（5 条规则、5 条 `safe-model` / `api.example.test`），没有 Max profile。当前 `BIGSMALL_VLM_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY` 仅检查 presence，均 false；项目 `.env` 不存在。精确入口 token 扫描未发现同用户运行的项目 app。

应用按 `MODEL_CONTROL_DB` 或默认路径加载数据库，secret 使用 `InMemorySecretStore`，生命周期为 session-only；CLI 独立使用显式 `--secret-env`（默认 `BIGSMALL_VLM_API_KEY`）。DB 中 `api_key` 被强制置空，因此 DB 记录或 shell presence 不能证明其他 app/session 全局没有密钥。本预检没有扫描全 home、外部账户或 secret manager，也没有检查进程内存。

型号保持 `qwen3.8-max`。[阿里云官方型号页](https://help.aliyun.com/en/model-studio/qwen3-8-max) 确认此 model ID，并公开 `qwen3.8-max-0902` / 日期别名；这不能证明用户 Token Plan endpoint 为此账户提供该快照，故本次没有替换型号、修改 registry 或 profile。既有闭环实验使用 getpass、密钥仅在当时内存，记录 35 次请求与未知账单金额，不能恢复为当前 app profile。

当前 T3b 原件只有两份 NOT_STARTED dry-run，无 actual bundle/attempt。`RoleRuntimeBinding` 要求当前 cloud snapshot/request settings、edge policy 与 cloud/edge/device 实际源文件 hash 均匹配；无 Max profile 与真实当前 probe 时，这项状态保持 NOT_EVALUABLE，历史实验不升级为当前角色/usage/billing验收。

下一次真实小探测的精确入口（本次未执行）为：

```bash
.venv/bin/python scripts/probe_rgbd_roles.py --config configs/research/ced_roles.yaml --output artifacts/research/process/20261004-ced-development/max-role-probe-real-NEW --profile-id EXISTING_MAX_PROFILE_ID --model-control-db data/model_control.db --secret-env BIGSMALL_VLM_API_KEY --execute --allow-paid
```

入口需已存在的 enabled compatible Max profile 与明确的环境 secret；不要把 Key 写入参数、报告或 Git。现登记为 S01、seed=0、320×240、pixel、grasp v2，cold+3 warm 共 4 个固定 nominal attempts，无 dispatch；入口会为观测启动 renderer。本次不运行 renderer。输出是角色规划探测，不自动证明物理/边缘/G1，也不提供实际账单。所选 profile 的 max_tokens/timeout 才是该次请求约束；当前没有真实 profile，未推定金额预算。历史20例/60请求预算仅属于旧实验，不套用到新120例 pilot。

最小下一步是恢复或配置受用户授权的实际 Max profile 和明确 CLI secret 路径，再执行上述4次角色探测、保存原件并按当前源验证；无需重复询问早前配置问题。更大的 `ced_selection.yaml` 仍有 pools_path/role_probe/protocol_evidence=null，暂不具备真实120例执行条件。

本次 provider/API模型、renderer、physics调用均为0。仅新写本目录 report.md/report.json/read-only-commands.log；不修改 core/tests/.env/profiles/DB/Stage/Git。详细公开profile字段、存在性与hash见 report.json。
