# R497 — 一次独立 byte-native JSON backend 资格与对照

实际规划模型：gpt-6-astra；仅规划。输入路径、bytes/SHA256及完整步骤见 plan.json。

批准一次 llguidance1.9.1 候选，明确替代 R496 的“不再试框架”和旧CPU截止边界；LMFE 仍以兼容性负结果封存，不再修复。R496合法末尾反斜线/quote仍被拒、后续审计超时，当前0load/gen；byte-native路线只是假设，必须通过实际资格。已核读官方 [API](https://raw.githubusercontent.com/guidance-ai/llguidance/main/python/llguidance/_lib.pyi) 与 [schema规则](https://raw.githubusercontent.com/guidance-ai/llguidance/main/docs/json_schema.md)，实际固定wheel定义优先。

1. 复核冻结输入和PyPI metadata；严格既有 enp7s0/AliDNS/TLS、无代理、精确 files.pythonhosted.org 下载唯一3,071,973B wheel，SHA256 dfac6021d9c4c5ef16b3a1d336c05ca5e8208ff30dec29d1c63ebcafbee3a346 后离线无依赖安装。新 runtime-llguidance-round497 只显式借用旧FLA+baseB，保护原71版本/来源，只新增1包共72；不得引入旧LMFE overlay、升级或编译。
2. 冻结实际公开API与tokenizer序列化副本；LLTokenizer使用真实词表和原三EOS，逐ID/特殊分类/ByteLevel字节规则及Unicode组合核对。完整原schema编译，strict选项，不删关键字；支持时开启general Unicode escapes。固定属性顺序等限制明确披露为生成语言子集，原提示与终审不变。每请求新matcher，单token消费真实suffix、1030prompt不入parser，无强制token/回溯；检查显式error状态。mask转真正硬屏蔽，越界vocab禁用，非终态三EOS全禁/终态全可达。
3. 原6合法、11非法、4值边界按原schema逐项核定预期，真实token重放≤120秒；含中文、emoji、尾反斜线/quote、结构/enum/长度/数值、EOS、prefix/缓存隔离，所有原合法fixture原字节必须通过。新codec/config dryrun及R494环境/硬件证据均通过才准模型。失败即冻结该候选负结果，不换第三框架、不修库或放宽schema。
4. 原A八请求 FREE/JSON/JSON/FREE/FREE/JSON/JSON/FREE，thinkOFF、原1030token/视觉输入、FP8/SDPA/512等全部不变，一次load、无warmup、每请求180秒，记录完整raw与约束开销、严格JSON及定位。B只有约束4/4严格PASS、专项来源计划完整且能按时结束才执行；不足记NOT_RUN。原始失败、代码、环境均保留，仅新增artifact/overlay。

预算仍原90分钟，**16:19:20 UTC硬截止**；本候选依赖+CPU最多15分钟至 **15:43:20**，A至 **16:00**，条件B至 **16:04:20**，末15分钟报告/Git。最大1load/24gen不变，不重试或延时。软件、真实生成、格式、定位和正式验收分列；交付仅明确artifact路径，保留失败及子集限制说明，沿用原R491分支父254a275与正常审批/三SHA核对，保护共享状态。
