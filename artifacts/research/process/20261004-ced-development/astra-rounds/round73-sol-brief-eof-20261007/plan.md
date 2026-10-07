# Round73：Sol brief末尾空行限定修复计划

状态：PLAN_ONLY_NOT_IMPLEMENTED。仅文档修正，不暂停独立P1，不代表产品验收。

## 失败证据

artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/executor-brief.md:103: new blank line at EOF.

以上由ROOT转述原Git检查输出，非本代理独立日志。随后stat使包装命令exit0，不能掩盖Git检查失败；未commit/push。独立读取brief确认10840 bytes、恰有两个末尾LF。

## 输入SHA256

- AGENTS.md：8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649（1774 bytes）
- artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/executor-brief.md：2433e7230c4ade2de9a5fae2febebf627ae4c10d7bb00f3c592227798d9374b4（10840 bytes）
- artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/document-verification.json：0f6a8c539222a83ad9a7b0707281ecf0864af1ca312f9819d0158b22216da9bb（1284 bytes）
- artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/dispatch.json：f1286724fa1b9bf547a322f6614b2ed11d94a8b7bb2f9650bf4feba5ecc8e2f8（834 bytes）
- .superpowers/sdd/2026-10-07-t12-sol-execution/progress.md：7c2cde3e8e8ee09328168ba44167556d7caa2106bfd34e79e816515bcceca75c（5087 bytes）
- artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/delivery-paths.txt：a081b7565305b345b64d6ddc759629a192474ca9ab7028cc507e34a13e3fb211（2100 bytes）

## 实施与验证

1. 实施前重验输入SHA256。将原brief及两个依赖JSON按原字节复制到本轮failure目录并记hash；原brief二LF备份仅本地保存，不stage、不纳入delivery-paths。另可生成base64 JSON公开封装原字节，须解码验证SHA/bytes完全一致。将ROOT提供的原git检查输出存为标注ROOT转述的文本，不冒称独立捕获。不得修改原件字节或Git whitespace规则来过检查。
2. 仅对executor-brief.md做 new=old[:-1]，删除最后一个LF字节，保留一个LF结尾。断言new+最后一个LF字节==old；由逐字节关系证明正文语义未变。预期10839 bytes，SHA256 24ada018c51dd2968dcebbdfefb742ff80eb50fafec0f7597ecf49f18b2dae93。
3. 仅更新document-verification.json中executor-brief对应的sha256及bytes；仅更新dispatch.json的brief_sha256。其余JSON值逐项相等，不改派单状态、agent_id、权限或验收值。历史原件已保存，不把旧验证记录说成覆盖新字节。
4. 仅在.superpowers/sdd/2026-10-07-t12-sol-execution/progress.md原内容后追加一条版本修正，记录旧brief hash、新brief hash、单字节原因、本轮计划与语义不变验证。保留旧hash及全部旧行；写前保留旧长度/hash，写后断言旧字节为新文件完整前缀。ledger保持现有Git交付边界，不借本轮扩展索引。
5. 生成本轮实施步骤报告，列出失败来源、备份SHA、字节等价、JSON限定字段及ledger追加证据。只对delivery-paths.txt追加本轮plan.md、plan.json、步骤报告、原失败收据及必要base64 JSON/原件manifest的明确路径，保留原21行及自身条目，不加入本地原brief备份或正在执行P1的任何源/报告。只运行文档检查，不重复产品验证。ROOT按三条文档修正路径、delivery-paths.txt和本轮明确新路径重新stage，禁止整体git add；原21项保持。之后一次独立git diff --cached --check，直接捕获其returncode/stdout/stderr，不用后续stat退出码替代。通过后按既有交付流程操作，本代理不提交。

## 前置与验收边界

所有输入hash须仍匹配，使用已可用.venv/bin/python；ledger仅追加，交付清单保留原21行。允许修改brief、两份依赖JSON、明确ledger和delivery-paths，新增证据限本轮目录。不得改变产品、原Astra输入、其他计划、Git whitespace规则，不执行产品测试、网络、模型、renderer、actual。

验收要求删除恰一个LF、摘要同步、正文逐字节关系成立、历史原件与旧ledger保留，随后一次cached diff检查真实exit0。开发验证、真实运行、正式研究分别未执行/未验收。新根因或计划外失败下一轮Astra；独立P1继续。

本代理只写计划两文件，未实施修复。
