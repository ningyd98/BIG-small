# R279 源码读取展示边界处置计划

实际计划模型：gpt-6-astra。仅规划，等待 ROOT 接受。

原 nested read bb4b65 实际 exit0，但一次打印包含合同、release、四份源码和模板的大 JSON，原始 53480 tokens 超过请求的 52000 展示预算，actual.output 带 Warning/truncated。随后外层 JSON.parse 在首字符 W 失败（exec_main.mjs:5:14）；这是实际解析失败，不是产品或 shell 失败。原件 230945 B / 2ed89e47bd68b54c7c9ab4436ab09d013672d89010494364e54ed41bdb4cddd7 保持原字节。无候选、runner、控制写入；外层 numeric/structured actual/独立流仍 null。

放弃原 aggregate read、parse 和 cache，不重放，不剥 Warning 或补尾。恢复范围仅为已批准 R278 源准备：唯一 Sol 从四份完整物理 draft 和冻结 R268 模板取得真实文本，依原计划形成新 main/consumer/完整候选；R277 已接受的 worker_object_id 绑定保持。

plan.json 与 input-observation.json 列明十四个完整输入 pin，以及六个可用文本范围：四 draft 各一段、模板 1–600 与 601–1115。每次独立纯文本读取先核全文件身份和行范围，再核段字节与 SHA；每段≤600 源行，总返回≤40000 UTF8（本次最大正文33590 B）。使用绝对 .venv/bin/python、明确 cwd，足够 token 预算并在打印前检查字节上限。保存实际调用/回执后才展示；不打印大型 JSON/base64，不将展示 framing 当 JSON。若截断或新错误则保全 STOP，不自动重试。

四 draft 完整 bytes/base64/mode 已物理核对；新 plugin20953/48e4 与 R277 acceptance 相符；runner 当前不存在。R278 full draft manifest 继续作为 before 权威，未知 partial main 保持 null。完整新候选必须先持久保存，再逐字节与 native 参数及实际 after 核对。原候选、计划、native、失败原件不改；ROOT 仍须全文审阅语义、native、输入、argv 和角色门。

本轮新增 runtime/test/static/SQL/Git/review/validator 槽均0；R276 三个 once 各0/1保持。没有产品、测试、上下文或角色变更，没有行为通过声明。规划展示 adf60b exit0 尾部曾被工具截断，未解析或拼接，不据其声称完整 release 全文；真实完整回执保存在规划证据中。

冻结后 STOP。ROOT 接受仅恢复源码准备，不释放任何运行。
