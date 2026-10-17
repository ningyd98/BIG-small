# R216 — ROOT 回执字段读取恢复计划

实际作者：gpt-6-astra；实施 actor：ROOT。仅元数据，等待 ROOT 门控。

28b525 实际 exit1：ROOT 使用不存在的 actual_command 字段；R214 实物字段为 transport_command。已返回非正文元数据与 initial==actual，但未展示365行/step或完成传输比较。原失败 invocation 源字节未导出，独立流未知；不补造。原 R214 87810e exit0 的读取保持 spent1/0。

本轮只允许 ROOT 新保存 implementation/view-compare-receipt.py，再完整读源码、固定SHA与精确 argv/env 后执行一次（120秒）。不用原错误 reader，不执行原 Sol reader，不改任何测试、产品、旧回执或角色额度。九个真实输入 pins 和逐项具名检查在 plan.json。

验收器严格使用 transport_command，比对原计划 exact transport/argv/env、4文件SHA、7 ranges和R215更正的365行。编号正文按 chr(10).join 构造并逐字节比较，保留真实空白。现有完整 output 为15116 UTF-8 bytes；原≤36000上限保留。先构造完整展示，再要求≤48000 UTF-8 bytes：打印一次已有365行及完整step和小型具名结果，不重复 initial 或巨型 command。完整结果独占写入新文件；输出不得截尾。

ROOT 正常 source gate 必须先于唯一新 metadata verification。实际工具返回立即保存，未知独立流仍null；所有 checks 真正通过且 ROOT 完整读正文后，才可原生新建 R214 root-acceptance。独立 R204 writer2 源码准备已由 ROOT 依据成功的 Sol87810e 阅读恢复，可继续，不依赖本 viewer 修正；未增加源码范围或执行权限。T2 RED 与 R214 最终验收仍 HELD。任何失败 STOP，无重试。R211/R213不回滚；R214旧465统计原件由R215解释，不重写。

新增产品/测试/静态/Git槽为0；父T2 RED/GREEN仍各0/1 HELD。当前测试合法追加不以whole-file旧SHA误报漂移。此轮不证明T2行为、T12、native或formal完成。保存后STOP。
