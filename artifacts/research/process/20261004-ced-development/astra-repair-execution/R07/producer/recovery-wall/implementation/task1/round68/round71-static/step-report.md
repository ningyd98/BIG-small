# RW1 P1b 格式与窄回归报告

状态：VERIFIED_RW1_TASK1_AWAITING_INDEPENDENT_REVIEW。实际agent /root/sol_t12_p1，按最新派单接替旧ROOT作者，不声称旧线程恢复或服务内部模型身份已独立核验。

round71计划47限定pin实施前全部匹配；沿原round68/round71-static新独占目录保存两源source-before/after和完整diff。指定ruff format一次exit0，完整producer仅新增1空行；tests新增2空行并将原103字符断言换行。已人工逐hunk审读，完整模块ast.parse(type_comments=True)→ast.dump(include_attributes=False)精确相等，没有任何AST归一化。函数名称/参数/装饰器/body、所有评论内容及类型注释相等。ast-equivalence.json保存精确源和AST哈希、评论及原82节点。

原round68 82/82 GREEN（32deselected）与producer mypy成功收据按完整AST等价条件复用，测试preformat hash与格式后hash分别记录；不复跑82GREEN/mypy/RED/collect/platform。指定两文件Ruff check与format --check各一次exit0。指定原pending_regression一次：19唯一节点、19通过、0失败/错误/跳过、95deselected，pytest45.25s、wrapper45.463867s。未假定32例或把19重复计入82独立分母。

两源已静止冻结；47限定历史/配置/角色/保护输入仍匹配，唯两源为批准格式差异且AST精确等价。旧81/1 fixture失败、82成功及两项静态失败均保留旧字节，不回写旧收据。新CPU原件完整清单见cpu-originals-denominator.json，清单不声称完整远端raw/DB包。

作者仅完成RW1软件验证，待不同作者独审。RW2/3、恢复0002、teacher窗口、actual/网络/模型/物理/正式研究未执行或验收；本作者不commit/push。
