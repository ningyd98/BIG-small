# CPU 原帧基准：单输入 provenance 与三项静态修正

规划角色：AGENTS.md 指定 gpt-6-astra；父轮 `round-p0-teacher-action-window-next-20261120`。本轮 PLAN_ONLY，未修改工具或产品，未启动基准计时。两个问题分别记录，限定同一工具内的小修；不改变父计划的任何实验条件或验收。

## 原始失败与已核实输入

原始 `preflight-first.stderr` 记录 `preflight` 在父计划 inputs_sha256 的 `src/cloud_edge_robot_arm/research/native_checkpoint_diagnostic.py` 拒绝 SHA 漂移，未进入实际帧资格和计时。原计划 SHA 为 `a1c22853004ddddcbc12bdd3c4726d2dc54f7925fe6537d37c6887b5e965073d`，当前工作树为 `b83983a9a76e20b25fbc7f2f2dc8041f0ee3bd8810704d66cd8cb756cdbc4d15`。与父代理说明的其他获准开发一致；本轮只确认字节不同，不撤销或改动其产品修改。

本轮实际读取并哈希，原实测 `checkpoint-egl-development-20261120/source/` 同路径仍为原 SHA；`git show 1c50c2d712f2eb16b5fb27edf76e7d78b5dabdd3:<path>` 和 `git show 902c2702:<path>` 均互证原 SHA。其余当前输入没有获准替换规则。父轮 plan.json 保持原字节及 SHA 3c10462457e761865c22c2bec2be231c5513961da8b90cbc535754ceed855eca。

独立问题：`ruff-first.log` 报 benchmark 工具两条 F401（io、datetime.datetime）及一条 B007（汇总循环未使用 aid）。这是工具静态问题；与输入漂移不同根因，不得借机重构。已有五项预期 RED 和五项初始 GREEN 日志保留，不能覆盖。

## 精确授权修改

仅修改父轮 `benchmark_original_frames.py` 与针对本轮边界的工具测试；新回执/报告写本轮目录或原私有 X 的新名称。不得修改生产 src、父计划、原始日志、冻结源码、登记或实际原帧。

1. 在父计划 input 解析中增一个精确的、不可自动扩展映射：仅 inputs_sha256 中上述完整 key 且 expected SHA 等于原 a1c22853 时，解析到上述原实测 source 目录同路径。映射目标必须真实路径、无符号链接逃逸，实际哈希等于原 expected。该条仍算被验证的一项，不可跳过或拿当前新 SHA 代替原 expected；其余 28 个 inputs 和全部 1212 frame inputs 保持原校验。缺失/坏 SHA/其他 key 漂移仍硬拒绝。
2. 回执记录 original key、父计划 expected、工作树观察路径/当前 SHA、resolved frozen path/SHA、本轮计划 SHA、Git 互证来源。当前工作树文件只作观察，不作为离线历史输入；运行前后若它再次改变须显式记录，不允许隐瞒。冻结副本或任一未豁免输入变动仍停止。导入继续使用原冻结源码，不引入当前 checkpoint 实现；保留实际模块 __file__/SHA 校验。不能让 resolver 成为任意 hash fallback。
3. 仅删除未用 `import io` 和 `from datetime import datetime`；仅将未用循环绑定 `aid` 改名 `_aid`。禁止 unsafe autofix、表达式/排序/样本/统计逻辑改动。

## 验证与运行前置条件

先保存本轮定向 RED：唯一登记 key+旧 SHA 能解析精确冻结路径；同 key 错 expected、其他 key 漂移、缺失/篡改 frozen、路径逃逸均拒绝。加入测试后只在原授权范围实施并保存 GREEN。执行文件实际测试名称由 Sol 定，但上述负控不能省略。

重跑原五项测试及本轮负控、针对工具/测试的 Ruff；保留首次失败。重跑真实 preflight，全部 29+1212 输入仍逐项被校验，source-freeze 全冻结文件、protected_inputs 全保护清单、inventory 全1228文件以及原模块导入核验继续运行，得到可审计的新输入解析回执。不得把软件测试通过等同实际帧基线资格通过。

全部修正与前置通过后，可恢复父轮尚未开始的 actual-frame 基线资格及原 CPU 配对流程；父轮原始 level6/1、全部242帧、4配对块、预热、预算、8秒门限、独立身份、零模型/模拟/真机/新正式组均不变。若之后出现新的基线不等值、资源超限、输入变化或计划外失败，保留原证据，停止相关工作并另交 Astra。不能用本轮授权处理后续问题。

## 验收与交付

小轮完成只表示单键来源约束已可执行、静态三项已解决、原安全/原件核验未削弱。记录实施 diff、RED/GREEN/Ruff/preflight 原件及 SHA，附步骤报告；汇入父轮，不宣称 CPU 收益或正式通过，资格仍0/9。按明确本轮/父轮工具路径提交，保留 Git 忽略的完整原始日志/输出边界。plan.json 列本轮直接原始证据及 SHA 和父输入映射，不替代父计划全清单。
