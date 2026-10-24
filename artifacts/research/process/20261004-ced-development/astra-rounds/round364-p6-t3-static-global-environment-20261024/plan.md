# R364：两个文件加载入口的静态全局环境更正

实际 Astra：`gpt-6-astra`，席位 `/root/astra_r363_plan`。仅 metadata；新增执行额度0，R363仍HELD0/1。

ROOT原tool `27b4b8`的独立审查中，仅runner/observer global closure两项false，全部未解析名均为`__file__`。完整原结果已保留为诚实标注的转录，原始命令/raw仍在工具历史；原false与all_pass=false不得覆写。其他完整diff、AST/source/hunk覆盖、protected-profile、常量/helper、零native调用检查沿用原通过证据，不宣称重跑。

根因是ROOT检查器只建模module assigned/imported/namespace符号及builtins，遗漏了这两个明确文件加载入口提供的`__file__`。这不是已证实的候选源码错误，也不意味着所有模块都必有`__file__`。

ROOT先核对intake及八输入SHA，静态确认R363 launcher以文件路径启动固定runner、pytest通过固定PYTHONPATH的`-p r363_live_observer`加载文件插件，并确认现有路径/pin guards。只对这两个准确文件的module环境增加单个`__file__`，其词法子作用域的global查找使用同一环境。原symtable算法和其他名字规则不变；禁止任意白名单或通用dunder豁免。`module.__file__`是属性访问，不作为free-global豁免。

先复现原未解析集合：runner的top、verify_lineage、verify_gate、run_selected各`__file__`；observer的_startup_contract中`__file__`。再运行上述窄更正，要求两集合均为空，输入前后hash一致。所有动作仅text/AST/symtable/hash，不import或运行候选。

ROOT新增`root-global-environment-check.json`记录原/新集合、入口证明、唯一环境补充及pins，再新增`root-global-environment-disposition.json`解释原误报。八输入清单详见plan.json；两可变ledger当前pin只用于本轮不变性核对，不得作为后续R363 runtime gate的immutable pin。

不得改runner、observer、proof、原检查、任何输入或ledger；不得新增执行额度、重试、测试、DB或探针。更正成立只接受声明入口下的静态名字闭合，不接受运行或研究行为。R363原gate/acceptance/实际运行前置/预约要求全部保留；其他未解析名、输入变化或新失败返回实际Astra。
