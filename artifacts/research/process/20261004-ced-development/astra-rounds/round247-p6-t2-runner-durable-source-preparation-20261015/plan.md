# R247 运行器持久源码准备恢复计划

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`；只冻结计划。

原调用因易失store返回undefined，在parent.slice处抛TypeError。该调用尚未进入nested工具或写新runner；无numericexit/structured result/独立流。原1199B错误记录及两行前缀保留，完整失败JS未归档则保持null，不补造。

弃用旧易失store，不重放失败JS。唯一Sol从现存R237 implementation/run-command.py完整35570B / 702954cd97555b37d6dba208ed5ba219a1ed4c7ff6510b025ae8ab860c81bd3c读取并核pin，以其为参考准备原R242新runner。完整新candidate先保存到本轮implementation/prepared-run-command-source.txt并固定真实pin，再native创建原R242 runner；目标必须与candidate完整字节相等，保存patch、actual及差异，不能隐式改EOF。

fixture已是合法16527B/c14e1f7…，不再编辑。已写prepare19065B/0c236e16…及原native/finalization原件保留；如需补全原计划要求的per-command stdout/stderr，只可在完整before后完成真实捕获/确切物理映射，不造流、不放宽检查。两个作者脚本最终均须ROOT全文/SHA/argv/环境门。

R242/R245完整合同、35精确缺失登记、工作区持久basetemp、600+15、真实资源及正向legacy RED验收全部不变。零新运行槽、零probe/重放/AST/import/compile/测试/Git。三原槽仍HELD，完成本轮源码准备即STOP，等待ROOT正式门和逐项预约。
