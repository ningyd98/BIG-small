# H1 并发输出归属复核

复核实际 Astra 计划所列输入哈希。各并发组为四个真实 CPU `prepare` 调用，seed 为
42001–42004，分别竞争同一全新输出路径。每组保留四份输入、实际命令、退出码、
stdout/stderr 及唯一原始期次。[实际 Astra 计划](../../20261004-ced-development/astra-rounds/round-harness-source-ownership-20261118/plan.md)
[独立审查](../software-final-review.md)

| 验证 | 观测 |
| --- | --- |
| RED | seed 42002 唯一创建期次，并以 0 退出。其他三个调用各以 2 退出，但都转报了胜者的 PREPARED、期次和证据。 |
| 源码 GREEN | seed 42002 唯一 PREPARED 并以 0 退出。其他三个均为 NOT_STARTED 和退出 2，各自没有胜者的期次、清单或计数。 |
| 清洁轮包 GREEN | 源码树外的 Python 3.12 环境得到同一归属结果。已安装包位置和依赖通过检查。 |

规范输出路径的相邻 sidecar 以普通文件、无 symlink 跟随和非阻塞独占方式获取。
拿锁后再次检查输出路径。传给原入口子进程的文件描述符和封装描述符共同持锁至执行与
终态核验完毕。控制用独立 CPU 子进程确认封装进程被 SIGKILL 后锁仍保留，子进程
退出后原 inode 正常释放。已有输出、可信预委派拒绝、歧义 FileExistsError 和
失败后仍有阶段文件的处理均有回归。包装检查 seed、标记、实际模式和源码身份，
归属不明时保留实际退出或信号与 null 成本。七项控制首轮 RED 已归档，最终 86 项测试
和限定 Ruff 通过。[竞争 RED](red/result.json) [源码 GREEN](source-green/result.json)
[轮包 GREEN](wheel-green/result.json) [控制 RED](focal-red.log) [最终测试](final-green.log)
[Ruff](ruff.log) [复现脚本](race-reproduction.py)

轮包 SHA256 为 `787d6937ea7447c51282a159d4952da2b201dca193746dcbcedc4d2759a72270`，
大小 1,630,078 字节。此次验证未启动模型、渲染、GPU 或付费 API，实际执行动作数为 0。
完整源码、依赖路径及研究验收边界见原 H1 说明。
[构建](wheel-build.log) [清洁安装](clean-install.log) [清洁复测](race-wheel-green.log)
[文件与源码哈希](verification.json) [使用说明](../../../../../docs/harness.md)
