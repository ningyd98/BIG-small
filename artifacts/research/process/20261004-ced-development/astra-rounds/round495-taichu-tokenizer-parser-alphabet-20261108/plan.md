# R495 — 解析器构造时同步真实 tokenizer 字符集

实际规划模型：gpt-6-astra；仅规划。完整冻结输入路径、大小及 SHA256 见 plan.json。

原 R493 过滤新增集合精确为 {248040}，但三个中文合法 fixture 在 target_label 的“红色”后拒绝普通 token125872“方块”，ASCII fixture 完成；尚无模型加载/生成。实际 LMFE 源码显示 JsonSchemaParser 构造时缓存 context.alphabet_without_quotes，TokenEnforcer 随后仅更新 parser.config，setter 没有同步 context。因此新假设是构造时默认字符集与真实 tokenizer 字符集不同。原失败、旧 backend、库源码全部保留。

1. 复核冻结输入 SHA/bytes；新 backend_r495.py 只在构造 JsonSchemaParser 时传入现成 CharacterLevelParserConfig(alphabet=data.tokenizer_alphabet)，再交给 TokenEnforcer。每请求新实例，其他配置默认值不变。不得人工追加中文、修改 tokenizer/Unicode 算法或第三方库。记录旧/新 config/context 字符集 hash、长度和“红色方块”的成员关系，验证新 context 精确等于 tokenizer alphabet 去双引号。
2. 新 cpu-backend-r495 报告重放原四合法 fixture、Unicode/转义、负 schema、1030-token 前缀和跨请求隔离门槛；中文 token125872 可达，非终态三 EOS 全禁、终态全可达。R493 regular tuple hash、精确过滤差集、原 EOS/HF 配置及 schema 投影必须不变。不得改英文、去约束、清洗输出或静默 fallback。必要新 runner 仅切 backend 引用及唯一输出名，保留原八请求顺序和所有模型/提示/图像/参数。
3. R494 fresh launcher 的 CPATH、warm JIT 环境和真实 cuda89/FLA 无 fallback 门槛仍必须通过；使用现有 73 包，不安装、不联网、不增加模型 warmup。若假设不成立或出现其他契约失败，保存负结果停止相关修复，不扩大范围。CPU 适配通过不代表模型 JSON/定位或正式研究验收。

预算仅在原 90 分钟内重分配：CPU 截止从 **15:14:20 延至 15:24:20 UTC**，最多新增 10 分钟从后续 A/B 时间扣除；整体 **16:19:20 UTC** 硬截止不变。本条替代 R491/R493/R494 的旧 CPU 截止，其他前置不变。最大一模型加载、24 次生成不增加；A 仍八请求，B 仍需原格式门槛及来源专项计划。步骤报告保留各层结论，交付沿用 R491。
