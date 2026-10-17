# R236 — 原始 bootstrap 异常采集计划

实际规划者：gpt-6-astra（/root/astra_status_plan）。本轮只冻结计划，实施和运行须 ROOT 门控。

R235 唯一恢复 RED 的三个用例均失败在 episode 前，child/wrapper 均为 1，accepted=false；没有达到原竞态断言或双库 COMPLETE。三个真实 poll 已进入本地初始化，具体内部异常仍未知。旧失败不改写，不能据此认定 JSON 修复完整或 Memory 原启动问题的因果已明确。

仅新增 R236/implementation/run-capture.py，由原唯一 Sol 作者准备。全部 27 当前源、211 保护文件、原测试/观察器/断言、event 三源及旧脚本保持原字节。复用冻结 R234 异常插件和 R235 import-only 插件，原 schema/round 标签不改。当前四个 target 的首行 242/417/654/420 与六个 serve 观察位置已核实；预导入在 pytest_configure，trace 在 runtest_protocol 才安装。

唯一新增槽为 R236_exception_capture：一次、600 秒子进程、总清理 15 秒，无重试；外层630秒及5秒强制终止边界。确切解释器、3个 node、两个 -p 插件、完整有限环境和独占新输出路径见 plan.json execution。没有另设 baseline、Ruff、SQL、比较运行或额外测试槽。

采集在同一次命令内先保存完整 current27 physical 快照，核211及两个插件、预导入模块、已解析历史证据和12旧数据库/36个缺失sidecar，结束后复核不变。只读文件字节，不连接数据库。原R235 baseline/history 的旧世代不得作为当前角色字节硬比；每个历史pin须对应原实物/完整原字节。新before/index记录当前世代。

保留完整 stdout/stderr、JUnit、3个case/trace、真实resource sidecars及summary、prerequisite、file/temp index、真实工具返回。异常保留有界cause/context/栈；startup仅原插件既存非原子观察。不开钟、不重采identity、不加wait、不包装产品函数、不改变授权。真实资源分母按本次观察记录，594不是预定数量；未观察的部分初始化对象、OS/native等不补造。trace/profile恢复、真实线程终止和进程组清理必须核实。

诊断 child0或1也必须完整保存原结果再判定。仅在exact3、源/资源/trace/前置及cleanup全有效时可记 diagnostic_complete；绝不记legalRED/GREEN。超时、缺件、截断、不恢复或新异常则原样保留并STOP，禁止重试。stdout摘要上限6000UTF8bytes，不打印完整嵌套原件。

实施顺序：ROOT审计划及索引→同Sol只准备新runner/明确diff/解析历史清单→ROOT全文源码与SHA/argv/env/transport门和单次reservation→唯一诊断→ROOT文件证据独立核对与本轮结算→STOP交下一实际Astra。R223四槽、父GREEN7和freshreview12保持HELD；Git0。旧R223/R232/R234/R235失败及旧settler都保留，不在本轮续接或修复event竞态。

输入索引 input-observation.json：216108 bytes，SHA256 59c169c2d58c5106e2503632081bc8546957ed9e3a5685a52ae7e46640a9330f。含21完整直接输入pin、27当前源、211保护、12数据库及36sidecar，规划metadata核对全match。一次可选大invocation显示出现工具内部截断，未解析/未冒充全文；该显示不作为完整合同来源，已如实记入观察。

ROOT仅可保存本轮gates/ledger/raw/findings/step；如需阶段事实，先完整before+CAS，仅STATE planning.R236和PHASE追加，其他字段与旧roles不动。产品/T2/T12/native/formal均未验收。完整可执行合同以本目录 plan.json 为准。
