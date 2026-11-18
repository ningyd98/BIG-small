# Astra：H1 CLI version 参数窄修复

实际模型`gpt-6-astra`；状态PLANNED_NOT_FIXED。`harness/cli.py`第42行注册`--version`时提供`version=`却遗漏`action="version"`，argparse默认store action不接受该关键字，造成原19项中18项同根因TypeError；包内helper项已通过。另有Ruff六项纯import/长行格式问题。三项输入SHA已实读核对并保存于`plan.json`，原失败日志保留。

仅在该CLI注册补`action="version"`，修复报告中的import排序和换行，不改其它行为；随后原19测试及相同Ruff范围复跑，并在源码树外清洁wheel环境核验help/version/offlineprepare。保存命令/退出码/安装证据；0GPU、0API、不扩大实现、不改变断言或正式验收。新失败转实际Astra下一轮。本计划不修改产品代码、不运行测试。
