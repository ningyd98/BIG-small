# 独立 EGL 读回器两处 Ruff 导入顺序

独立读回软件验证 14 项通过，随后 Ruff I001 在新增 read_checkpoint_egl.py 和 test_read_checkpoint_egl.py 各报一处 import block 顺序。与组件辅助调用兼容属于不同根因。

仅在上述两个新增文件按 Ruff I001 重排导入。保留原导入成员、别名、from __future__ 首位、执行绑定与其余 AST；不更动读回断言、来源、guard/owner 时钟、schema、报告或产品。不要借此批量格式化其他文件。

保存首错与已绿测试回执、修前源码 SHA；在可重建当前软件环境下只运行两个文件的定向 Ruff I001 修复。

用前后对照证明非 import 语句 AST、各导入的名字/别名集合一致，Ruff 两处通过，同一读回软件测试14项及原有正负样例仍通过。此独立机械修订不阻止产品准备；真实读回按父轮独立进行。
