# R282 可选摘要展示器处置

实际模型 gpt-6-astra，仅规划。原 b66be5 exit1 在 Path(list) 失败：viewer遍历混合 roles.items()，错误把非路径 keys 列表当路径。原运行8b8811已结束，viewer没到summary写入；不影响raw/result或角色。

直接ABANDON原viewer：不修、不重放、不另造汇总、不补写缺失输出。ROOT3aca9d是独立成功物理观察，不把它改称原viewer成功。必要后续角色读取只选固定ROOT/AUTHOR项；本轮不新增读取/验证流水线。

五输入完整pin见JSON；原exactcmd/actual/独立流null保留。R281行为失败与R283门禁问题单独处理。产品/test/runner/roles/STATE/PHASE无变；新增runtime/test/static/SQL/Git/review/validator额度0，旧额度不重置。冻结后STOP等ROOT。
