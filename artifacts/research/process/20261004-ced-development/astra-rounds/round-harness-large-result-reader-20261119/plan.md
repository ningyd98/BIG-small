# 正常 Harness CLI 读取其自身生成的合法大结果

## 实测与原规则

- 第11个真实样本由冻结4bdb64eb原生入口生成，result.json 8,606,790字节，manifest 中长度与 SHA 对应；CLI 执行后核证及独立 evidence 命令共走 verify_evidence，读取 result 时触发通用 8 MiB。原 native 0、wrapper/进程 2，成功证据由独立大文件读回得到。原批终态不变。

## 限定工作

- 只在新研发候选修 src/cloud_edge_robot_arm/harness/evidence.py 的 manifest 绑定 result.json 特定分支及 tests/test_embodied_harness.py 定向回归。普通 manifest、scene-assignment、source 及其他现有 JSON 保持旧范围。result 设单独有界容量（本轮建议 16 MiB，为原上限两倍，实测仅8.21 MiB），或实现同等离线资源可证明的有限流式读取。必须先验证类型、有限大小、fstat/manifest 声明，至多读取上限+1；在同一安全打开的 fd 上核全字节摘要，再按原 strict_json/真实 _episode_result、预期源所有权及文件绑定检查解析。支持原成功、失败、准备和旧版本合法结果；若阶段/来源不匹配仍以原行为拒绝。不要通过无界 json.load、绕过摘要、忽略超大字段、容许重复键/非有限常量或捕获异常后伪造成功修复。保持原 CLI 退出和未发布语义，只让真实校验成功的合法输入返回成功。

## 执行前置

- 研发独立 checkout；保护正在运行的 4bdb64eb checkout/已安装 wheel、原 BEGIN/END/包装 stdout 和所有 slot。先用旧版标准 CLI 只读见证 11 错误；新增可维护的合法大 result 夹具覆盖刚超过 8 MiB、专用上限/超限以验证边界。已有 paths/links/manifest/ownership 负控继续；新负控至少覆盖大 result 大小或 SHA 不符、畸形 JSON、manifest/assignment/source 大文件仍拒、声明小实文件大。

## 验收

- 正常新候选命令 bigsmall-harness evidence <按当前 --help 的真实参数> 从原11只读产出 VERIFIED，准确返回原 episode 标识、大小/manifest SHA、组件/计数，另以现有 expectation 正负例验证集成。覆盖 cli.py 运行后 verify_evidence 调用链，可用软件夹具/已录 provider 替身，零新增付费模型/真实槽。报告新旧 CLI 的版本/源、各退出及实际测试与 Ruff；原批继续按旧版本，不回写原包装，后续软件发布另核。
