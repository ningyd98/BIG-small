# R395 嵌套工作区 status 参数对账

实际模型gpt-6-astra；代理/root/astra_r389_revalidate；2026-11-02T12:00:28.873019+00:00。

已明确定位显示参数差异，原guard数值不用改变。原R393命令带`--untracked-files=all`；独审和新git_guard.py漏此参数。当前相同all命令原生输出精确重现2481192字节/SHA3330c4201b2a2b1bddc1df4f967049d3d3e89cd413017140b8bdf1ba1deedf54；default输出精确重现2481167字节/SHA025f68d1aaa8344ff78a20d4f3db98c1c2a2f4811eae5196e0d72c4587daacf1。

两份真实NUL记录唯一差项是all的`?? tests/fixtures/t5_gripper_dev_cases.json`与default的`?? tests/fixtures/`目录折叠，恰差25字节。该实际路径lstat普通文件11709字节，ls-files无记录、check-ignore退出1，无payload读取。没有删除/恢复文件或改ignore。原历史完整stdout确未持久化；现在保存的all输出明确是当前重放，不能称为旧原文。相同hash证明状态序列相同，不是完整untracked载荷字节审计。

## 限定修改和恢复门

仅准local-only git_guard.py nestedstatus调用补`--untracked-files=all`，同时将候选输入v2绑定v3；原两个statusguard、HEAD、refs/index、trackeddiff和source保护值完全不改。git_command.py保持。先保存helper原字节，再静态复核精确diff；预期修后SHA `c72d9d810a0b8be48129b47073b8a9a1ac0e5bda2ff9030d2541c59d4eb0c186`。

保留blocked独审及其Important。候选v3由已审217项加本轮窄小记录组成，重新冻结真实counts/bytes和NULpathlist；不覆盖v2。独立最终审查须以双命令原生证据明确解决R393-I1，确认helper参数和候选v3；可每nested各一次≤30秒同命令只读status复核，0retry。不为本次对账重复4亿字节trackedbinarydiff；近Git操作的原R393保护门仍照常。

只有独审接受、同参数status及所有原保护门满足，才启动原R393600秒管理clock并执行原限定Git流程。真正同参数漂移立即停，不刷新hash。R393的1commit/1push60秒/1exactlsremote60秒完全不重置；R395不运行任何Git写或网络。

## 窄交付附加

原R393/R394计划保持原件。只附加R395的plan.md、plan.json、original-finding.json、input-audit.json、step-report.md、review-resolution.json六个小记录。完整2.48MBstatus、beforehelper、行政helpers及大blocked/candidate回执按原界限留本地。9源+2summary和全部原38pins不扩大；raw/DB/gitlink等不纳入。

规划只读状态/归属/ignore/lstat和hash，并保存当前重放、audit、plan；没有嵌套写入、源码修复、测试、DB、网络或大diff复跑。交付本计划后停止其他工作，等待主执行器确认Git门。
