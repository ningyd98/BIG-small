# Astra：先生成交付清单，再检查链接

实际模型：gpt-6-astra；日期：2026-11-17；状态：PLANNED_NOT_IMPLEMENTED。

原始失败见主轮`implementation/delivery-manifest-attempt-1.txt`（chunk bafd8f，rc1）：内联工具在写出delivery-manifest.json之前检查phase-summary.md对该文件的链接，引发AssertionError。根因是工具构建顺序，文件目标与引用均正确，不是文案错误。失败、阶段/步骤报告、前三轮计划/清单及三正文共15输入已冻结，路径和SHA见plan.json；快照仅本地保存。原35/35文档检查PASS不受影响。

限定实施：

1. 实施前复核输入SHA。保持全部正文、检查断言、phase-summary链接、原失败日志和已冻结计划不变。
2. 从前三轮明确交付清单与本轮新增文件组成精确路径列表；先写本轮简洁`implementation/repair-report.md`过程记录，再读取各已存在文件SHA生成主轮既定`implementation/delivery-manifest.json`。清单列出自身路径但自身SHA为null，并注明SELF_HASH_NOT_RECURSIVE；其他文件必须真实存在且有真实SHA，不用glob收集无关文件。
3. 清单写出后再进行完整拟交付集合的JSON解析及Markdown本地链接检查，逐项重算非自身清单条目SHA；不删除链接、不放宽断言。修复报告补写实际验证结论后允许重生成清单一次并重新核对，使最终报告SHA一致；不能声称尚未执行的检查通过。
4. 本轮仅工具排序修正，不再重跑35项正文检查或任何产品测试。可以执行所述轻量交付检查、只读Git、git diff --check。保留本轮简洁报告中的命令/退出码/结果，报告不需要记录自身SHA。
5. 允许在/tmp生成精确路径列表的NUL文件，以Git pathspec-from-file/pathspec-file-nul或等价明确参数暂存；检查实际暂存路径与清单一致。沿用原授权commit/push并核对本地HEAD、上游、远端三SHA。已有无关改动不带入，不强推。预期沙箱权限限制按工具机制升级，实质意外失败交Astra。

远端交付仅在既定清单追加：主轮`implementation/delivery-manifest-attempt-1.txt`，本轮`plan.md`、`plan.json`、`implementation/repair-report.md`。本轮inputs/original仅本地保留。本计划是前三轮精确交付清单的追加授权，不改前三轮冻结计划字节。

验收：清单先存在，所有拟交付JSON可解析、MD本地链接存在、文件SHA与清单一致、三正文SHA不变、精确暂存且三SHA交付核对成立。文档检查/交付不代表Harness已实现、真实运行或正式研究验收。真实API/仿真/硬件仍需原适用计划、资格、安全和预算，此轮无实际产品运行授权。

若检查发生新的链接缺失、JSON错误、输入漂移或需改正文/断言，保留失败并停止相关修复，交实际Astra新轮次。不得为通过改动冻结证据。
