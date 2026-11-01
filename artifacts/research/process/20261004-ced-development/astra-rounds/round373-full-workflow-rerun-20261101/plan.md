# R373：全流程诊断重跑与问题总结

实际规划模型 **gpt-6-astra**，2026-11-01。用户已授权“重跑全流程，继续总结问题”。本轮只诊断、不修产品/测试；独立阶段遇到失败仍继续。当前 HEAD `8089743604be33ab107853f86894de211f7bf259`，保留并记录 dirty local_temporal 性能候选和两个嵌套工作区，不能把实际工作区测试结果只归给干净 HEAD。

## 阶段与上限

| 阶段 | 实际范围 | 单次child上限 |
|---|---|---|
| 全收集 | root已完成4732节点/283文件、exit0；复用preflight，不重复collect | 已用3.82秒，原上限180秒 |
| 静态 | root已完成Ruff format/check、mypy（均exit1），仅复用；继续compileall、docs、中文注释、秘密扫描、合同、pip check | 已执行三项原上限各300秒；其余各60–120秒 |
| 前端 | Vitest、两份tsconfig、ESLint/Prettier、Vite build | 各120–300秒，合计1200秒 |
| CED保护门 | selection/foundation/power各一次；本轮foundation来源的INITIAL拒绝 | 各120秒 |
| 普通pytest | 除专组外全部模块，排序后round-robin六组 | 每组900秒 |
| closure其余 | 当前94节点扣除T3九节点，排序拆三组 | 每组900秒 |
| 实际MuJoCo关键回归 | model load、protocol_raw_observers、rgbd_physical_skills三个完整模块 | 一组900秒 |
| P6 T3九节点 | startup memory/sqlite、UTC memory/sqlite、terminal三变体、public confirmed memory/sqlite | UTC各3600秒，其他各600秒 |
| 浏览器 | 默认E2E和研究E2E各一次、单worker零重试 | 900秒 / 300秒 |

精确命令、九个nodeid、环境与路径在 `plan.json`。节点互斥分配；全收集后明确排除 real_robot_runtime/isaac/isaac_runtime/ros2/real_rgbd_dataset/benchmark，并记录每个deselected节点，不能隐去或算通过。五个短UTC测试只在普通组中跑一次，**不能替代完整UTC两后端**。超时保留已执行和未完成节点，不自动重跑尾部。

## 前置与输出隔离

使用现有 `.venv`、`cache/node-v22.23.3-linux-x64/bin/node`、node_modules和匹配Chromium，不安装升级。不运行 `run_checks.sh`、`verify_project.py`、`npm e2e`准备脚本，也不source注入旧模型/Isaac/路径默认值的 `scripts/linux/env.sh`。不调用会回退全局artifacts根的verify_phase11_1；其他旧CLI未单独启动，已有软件测试覆盖范围如实记录。

closure使用原R235 prerequisite插件，新resource/prerequisite路径。`BIGSMALL_R158_COMMAND=final_new23`仅兼容label，R373真实stage_id另记。复制R166原始legacy-goldens到新inputs并校验，不生成新golden、不用t1_red。插件固定operational_time_v1 SHA已核对。

默认E2E用artifact-only配置overlay与新BIGSMALL_E2E_ARTIFACT_ROOT，排除研究spec后单独跑。研究config和spec都硬编码旧目录，必须复制到新artifact仅改路径/模块定位；backend与18MiB旧软件fixture也复制，新输出绝不写旧t17b目录。保留全部断言，4200条BLOCKED仍为软件fixture；默认合成MoveIt摘要也必须标SOFTWARE_FIXTURE。

CED不带execute/allow-paid/profile参数。预期exit3必须结合480/120/120分配及真实缺前置理由核验，INITIAL不发布。不可仅按退出码称通过，更不可伪造真实probe、标定、选择或冻结源。

## 执行与失败处理

允许root用小型subprocess驱动，直接文件流保存完整stdout/stderr，有限wait、独立进程组、TERM5秒/KILL/reap、总清理15秒、源pin和结果JSON；不再构造大型验证器。每阶段独立新目录/basetemp/JUnit，记录缺失、timeout和未完成项。无JUnit不能编成零失败。单stream异常超过256MiB则停止并明确OUTPUT_LIMIT/truncated。

默认串行；P6九节点串行lane不与广泛pytest、MuJoCo、浏览器/前端测试构建竞争。轻量静态和只读报告可在root记录重叠时并行，不能据此声称性能benchmark。首个失败不取消独立阶段，所有新失败仅归因汇总，不顺手修复。

只有明确工具/sandbox拒绝必要端口/系统/网络操作，才允许同源同命令新目录的一次环境重试，并且只能使用当前工具政策许可的escalation；若政策禁止，记BLOCKED_ENV，不绕过。产品断言、产品超时、缺依赖和普通TLS失败不获重试。

## 最坏时长与验收

P6预算 `2×3600+7×600=11400秒`，即 **190分钟**。所有正常child阶段上限合计 **24720秒（6小时52分钟）**，不是耗时预测。整批含准备、环境例外、清理和总结硬上限 **8小时**，末15分钟保留总结交付；到时未跑项明确NOT_RUN_BUDGET。root在启动前告知用户该最坏范围，持续简短更新。

R350 startup实测约316/318秒；R368仅首exercise约1113秒，完整UTC时长尚未实测。本轮3600秒是诊断上限，**原双backend合计600秒验收保持未证明**，即便较慢诊断通过也不能替代。完整节点必须获得本次实际完成或明确有界超时。

产出coverage-manifest、findings、step-report和phase-summary；每项失败绑定原证据、源hash、命令、事实与待证假设，按产品/测试fixture/环境/历史静态债务/真实前置缺失/UNKNOWN归类，再提出后续最小Astra修复轮次。软件、实际MuJoCo、浏览器复制fixture、真实研究分别记录。缺Max probe、独立标定/误差界、合格B0及各冻结链的真实环节维持BLOCKED，不产生新云费用或硬件动作。

新交付额度为一次远端预检30秒、一次正常push60秒、一次远端SHA核验30秒，不改gitconfig/TLS，不复用R372。显式提交新报告/计划与精选证据；不提交local_temporal候选、其他性能测试、嵌套工作区或批量raw/DB。三SHA不一致或网络不通，保留本地提交并如实报告远端未验证。

共55个直接输入bytes/SHA256见JSON；没有递归继承历史门禁。规划者只写本计划，未执行产品/pytest；root已完成的collection直接复用。

补充：root已冻结的1050源文件清单 `preflight/workspace-source-before.json` 和三项静态诊断原件直接复用，不重做收集/静态，不据新失败实施修复。8小时整批时钟从本轮root前置开始，不从计划落盘重新计时。
