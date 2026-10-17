# R280 native patch 文本边界处置计划

实际模型 gpt-6-astra；仅规划，等待 ROOT 审核。

原 R276 门禁 dda83b exit2，唯一报告失败为 `exact implementation patch`，在所有输出/角色/运行前停止。独立6426df字节观察证实：actual native 参数80042 B / 4e1fc083c306c3855d66eca42b1419f8492794ba9509f14074657edba0aea4e0 无末LF；归档80043 B / 9f2e2f774a4d798ec28e6ffc8055ef970f32beede263f71ed6b1851f5e12c7dc 严格等于参数加一个LF，首差80042。实际单Add重建与 runner/candidate78491 B / 50f38bb3d57e7d361283cf64adb97a8207b41445c17f8bce502bf8703ab430b6 全等。

根因为 ROOT 将归档表示误当提交参数逐字相同。以 receipt stages[1].arguments 为真实参数权威，归档只命名为“多一个 terminal LF 的归档表示”。两者及旧报告/native/失败一律不改，不允许 strip、normalize 或任意后缀豁免。原 native {} 的 numeric/独立流仍 null。

完整旧门17160 B / 2f2f0ab49b4251ae575d382fae8b8c6aa49c734fc5436ee5b3fb88f7a6a69ab4 已物理保存到 before，manifest含完整base64及mode33204。plan.json列十五输入完整pin、精确旧行及替换块。ROOT仅创建独立新门，替换该比较为 actual参数pin、archive pin和单LF关系三项检查；其余native重建、27/211、历史、数据库、角色/输出缺席和argv门全部保留。允许额外写本轮来源及完整检查报告，使 stdout≤6000 UTF8；无其他检查豁免。

新门先持久保存、完整读回/SHA/limited diff/native实际及literal argv经ROOT审阅，才能以固定绝对解释器、env -i、120秒执行一次普通metadata门。完整检查/失败写新文件，控制台仅真实counts/pins；原五个R276 gate输出仍须独占创建。失败保全STOP，不重试。全pass也仅源码/输入接受，运行仍单独门控。

没有 runner/plugin/product/test/STATE/PHASE/role 改动，没有新运行/测试/static/SQL/Git/review额度；R276三个once0/1不变。原dda83b保持失败，不声称行为或T2完成。冻结本计划与观察后STOP。
