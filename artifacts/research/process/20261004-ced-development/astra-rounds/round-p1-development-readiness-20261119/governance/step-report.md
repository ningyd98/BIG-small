# 文档治理核对

按 GPT-6.2 Astra 的 P1 方案核对文档检查器输入。基点 `b3fc6213aad819e2cc46a77a972de242d195a065` 的 `scripts/check_docs.py` SHA256 为 `d922e475de71052544c6a3a260648ad39acee8480f5bcb186aec5305749f1211`，与计划一致。`check-docs-before.json` 保留 25 条原检查顺序与分类，已脱敏。原 stdout SHA256 为 `b0879446d4fe5c3aa79e5b1ea975a60a044778df4a4025f8eadb7aeb85ccf850`，原件保存在工作树 `cache/local-verification/20261119-worker-docs/check-docs-before.local.json`。

| 原报编号 | 数量 | 核对与处理 |
| --- | ---: | --- |
| 1、8 | 2 | `final_acceptance.json` 两处指向原部署主工作区的留存文件，改为本机历史证据路径。 |
| 2 | 1 | `git_baseline.json` 已在原部署主工作区留存，改为本机历史证据路径。 |
| 3 | 1 | `git_delivery_provenance.json` 已在原部署主工作区留存，改为本机历史证据路径。 |
| 4、5 | 2 | 系统清单的 JSON、Markdown 均在原部署主工作区留存，改为本机历史证据路径。 |
| 6、7 | 2 | 依赖清单与磁盘记录均在原部署主工作区留存，改为本机历史证据路径。7 个本机文件均未入该分支索引。 |
| 9 | 1 | Isaac Sim `6.0.0.1` 为软件发行版。加明确版本标记，检查器仅在带版本标签且无地址后缀时允许此类表达。 |
| 10、11 | 2 | 原下载摘要含两处真实 IPv4。摘要保留接口与 HTTPS 端口，地址留在原套接字证据。 |
| 12 | 1 | Molmo+OpenCV 说明使用工作树相对的入口与清单，本机应用和缓存目录改为可配置路径。 |
| 13 | 1 | 历史项目状态的三条回执改为仓内相对路径。 |
| 14 | 1 | Sol+Molmo 单场景说明改用当前检出及可配置本机应用根，不依赖一位用户的检出目录。 |
| 15 | 1 | RGB-D 下载说明用用户目录变量保留原有本机库布局。 |
| 16、17 | 2 | RGB-D roadmap 的 `train_rgbd_decision_module.py` 是提案。保留文件名、参数与批次约定，明确待实现。 |
| 18 | 1 | 明示 `scripts/`、`configs/`、`dashboard/` 是三个实际目录。 |
| 19、20 | 2 | Astra 修复计划中的 `collect_native_calibration_v2.py` 是提案。保留原参数和启动环境。已存在的 collector 使用自己的入口与约定。 |
| 21 | 1 | Astra 修复计划的工作目录改为 BIGsmall 仓库根。 |
| 22、23 | 2 | T12 的 `validate_t12_development.py` 是提案，保留拟用参数和来源边界。 |
| 24、25 | 2 | 尖括号空格目标和百分号编码目标均为同一已跟踪开题文件，SHA256 `4fe39c32f990be2adc2789fba08c2600382c8a03247f9fef66ae6dc982288ccd`。检查器按 CommonMark 的目的地写法解包并执行一次百分号解码，两份原链接均通过。 |

原检查器按连字符跳过四段数字。收紧该条件时识别出 `docs/phase9_2_report.md` 中两处历史环境路径内的 Isaac 发行版，改为明确列出发行版及环境路径命名。真实有效 IPv4 的拦截继续生效，检查输出只列仓库相对文件和行号。

`checker-red.txt` 保存两个新增回归在旧版本上的失败。`check-docs-after.json` 为全扫描退出 0、0 条问题。`cli-controls.json` 记录有效链接/版本的正控和故意损坏的目标、脚本、IPv4 的负控，负控退出 1，全部命中。`pytest-governance.txt` 记录 8 项通过，定向 Ruff 通过。本轮使用本机软件校验。
