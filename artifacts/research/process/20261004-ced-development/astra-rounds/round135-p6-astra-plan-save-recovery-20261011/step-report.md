# R135 元数据恢复步骤报告

实际 gpt-6-astra 先保存 R135 MD/JSON，之后仅用结构化 apply_patch 保存 R134 计划及两次失败的可得文本。R134 的 78 个输入 pins 在保存后再次核对，零不匹配；六源与冻结原件保持一致，52 protected pins 全匹配。

18dc99 仅可靠保存错误片段与原 tool 引用；没有伪造完整独立 raw。90c536 保存完整工具 combined 返回；两个命令均未重跑。产品/测试源码、旧 plans/raw/账本均未修改，产品命令数 0。

R134 待 ROOT 复核激活，原 RED23 仍 used 1 / remaining 0；新 recovery3 尚未执行，四终门仍 held。所有计划与证据的完整路径、bytes、SHA256 见同目录 step-report.json。

