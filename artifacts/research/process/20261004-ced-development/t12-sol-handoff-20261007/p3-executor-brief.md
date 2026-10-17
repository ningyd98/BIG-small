# GPT-6.1-sol 后续派单草案：P3 软件与配置

状态：PREPARED_NOT_DISPATCHED。仅在ROOT实际派单、原单写者释放并复核输入后实施。继承原Astra总计划技术约束，不是新增Astra计划。

只处理下方Task3软件/配置差异和CPU验证。已只读确认现行ced_roles.yaml为pixel，role工厂已支持normalized_1000；保留原两图320×240及成功请求配置，不重建Max接口、不重跑35请求。4次当前源角色probe须待P8受影响源静止及ROOT运行前置复核，当前不授权模型/网络/渲染actual。

先保存owned源/测试前件并检查原成功公开证据，只消费现有secret引用而不读取秘密。三个已命名用例先RED后最小实现，一次owned GREEN及必要静态；原计划允许owned纯格式整理。测试验证实际配置、角色/source区分和所有sent成本分母，不以hash/flag制造资格。源只能改Task3列出的四路径；如cost ledger等额外产品路径暴露新根因或必须扩范围，保存原件交ROOT→Astra，不自行扩展。保持UTC/规则不冒称模型/LOCAL_RECOVER禁用等原边界。

输出写t12-convergence-execution/P3：公开差异表、role-delta.json、输入SHA、source-before/after、完整diff、逐命令原收据、唯一节点分母、步骤报告与显式delivery路径。实施者不派代理、不Git；不同作者独审后ROOT交付。

以下逐字继承现行Task3：

### Task 3: P3 — 复用已跑通Max，只对齐T12角色与成本绑定

**唯一交付/入口：** 用户确认Qwen3.8-Max已跑通；历史35真实HTTP200与独立valid=true支持该事实。无重新开通、重配账户或通用35call复测。

**依赖：** 无；可独立开始

**Files:**
- `MODIFY configs/research/ced_roles.yaml`
- `MODIFY src/cloud_edge_robot_arm/vision/role_models.py（仅发现必要差异时）`
- `MODIFY tests/test_rgbd_role_models.py`
- `MODIFY tests/test_ced_runtime_binding.py`
- `NEW artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/role-delta.json`

**Interfaces:** 复用现有角色工厂支持coordinate_system Literal[pixel,normalized_1000]及planner已有坐标解释；优先继承成功normalized_1000而非新建转换器。复用现有RoleRuntimeBinding和CostLedger。

- [ ] **Step 1:** 读取成功acceptance及其公共request/config/source索引，建立旧成功链路→现行T12角色差异表；凭据仅应用原secret引用，不读取/打印/复制或索要聊天明文。
- [ ] **Step 2:** 将现行ced角色坐标显式对齐normalized_1000，保留成功320×240双图、temperature0/max_tokens512/thinkingfalse的适用请求配置；若当前合法配置已一致则不重复改写。按现有role工厂测试实际参数，不从报告伪造不可变权重hash。
- [ ] **Step 3:** 新增test_ced_max_reuses_successful_normalized_transport，断言模型身份/两图/坐标链一致；test_existing_max_success_is_not_new_source_freeze，断言旧请求可证明可用性但不能替代新source绑定；test_role_cost_delta_preserves_all_sent_requests，断言所有sent超时/retry仍入账、未知账单null。
- [ ] **Step 4:** 只读旧公开原件完成差异核对。无变化部分复用旧证据；确有新增角色协议未被原件覆盖时，只登记并执行满足当前既有合同的最小有界请求集合，保留失败，不重跑35call通用实验。P9在任何actual前强制校验role_probe，因此不能等P9自身请求补这个前置。优先复用已经满足现行ced.role-probe合同的原件；若只有旧成功Max材料，则仅生成当前缺少的角色契约记录。现有freeze要求warm_runs+1完整，当前warm_runs=3时明确执行cold+3warm共4请求；这是现行角色/source的增量证据，不是重做连接可用性或35call复测。最终角色probe在P8受影响源码静止后绑定，P3软件/配置差异可先并行。

**验证/实际命令：**
```bash
.venv/bin/python -m pytest -q tests/test_rgbd_role_models.py tests/test_ced_runtime_binding.py -k "normalized or source_freeze or role_cost_delta or role"
```
```bash
MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_roles.py --config configs/research/ced_roles.yaml --output artifacts/research/process/20261004-ced-development/t12-convergence-execution/P3/current-role-probe --profile-id "$MAX_PROFILE_ID" --model-control-db "$MAX_MODEL_CONTROL_DB" --secret-env BIGSMALL_VLM_API_KEY --execute --allow-paid
```
- 上述actual命令只在无可复用的合格现行role-probe原件时执行；先核对全部受影响源码静止，4个请求严格沿现有合同。

**验收出口：** Max成功路径可由现行角色配置明确引用；源/hash/坐标/成本差异逐项closed或待特定actual。不再列“缺key/模型未跑通”为全局阻塞。

**失败停点：** 新角色差异导致明确失败时按具体新根因Astra；既有调用P95超5秒不放宽TTL，晚回复按现有预算新采集/拒绝路径处理。

- [ ] **交付：** 保存本任务局部报告、原始命令/退出码/完整stdout-stderr、输入输出SHA与actual分母；按下述显式路径Git规程提交。

