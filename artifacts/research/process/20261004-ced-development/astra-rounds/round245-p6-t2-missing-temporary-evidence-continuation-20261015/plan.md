# R245 临时历史证据缺失及受限接续计划

实际作者 `/root/astra_status_plan`，模型 `gpt-6-astra`。本次只冻结计划，不实施或运行。

## 已确认事实

ROOT与soleSol两侧均观察到旧/tmp文件不存在。独立核对原419输入：388当前字节一致，29缺失（24DB+5原metadata raw），另2项为已有准确归档的STATE/PHASE合法世代。加R239后续6DB，共精确30DB与5raw缺失；90旧sidecar目前也不存在。消失原因和时间未知，不归因于删除、重启或任何人员。

只检查明确R232/R235/R236/R237/R239及R240六目录：没有匹配大小的物理候选/DB文件；430份既存JSON、149773646B中未发现匹配完整literal/base64字节。这不是全局不可恢复证明。不重构JSON、不生成数据库、不把查询结果/manifest冒充旧原件。

## 精确缺失边界

input-observation.json.known_missing逐项列35个完整path/bytes/SHA、出处selector/ordinal及真实absence。只有这35个精确身份可标记HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245；不能按/tmp、扩展名或round泛化跳过。后续前后门仍核存在性，若重新出现则停下核来源，不自动采用。

旧实际检查仍是其发生时的历史记录；现在不能重新hash/query这些原件，也不能声称完整历史字节包仍可复验。旧报告/plan/source-index不改。其他固定输入、27源/211保护、R239完整fixture物理档和所有明确历史归档继续严格检查。两个STATE/PHASE世代差异不属于丢失，沿原精确archive映射处理。

## 接续R242，仅两处元数据约束变化

1. 原30旧DB及5raw的无法完成字节检查改成精确缺失状态报告，绝不写hash-match=true。新接受结果明确为带历史证据缺失边界的受限新运行资格。
2. 原RED的唯一`--basetemp=/tmp/bigsmall-p6-r242-red`替换为R242工作区内`implementation/red/persistent-basetemp`。该路径必须首次运行前不存在、非symlink；禁止让pytest清除既存数据。其余argv/env/600+15/节点/插件完全不变。

soleSol仍仅按R242改release.wait调用两个字节并编写原两个新作者脚本。R245不增加脚本层或执行槽。三原槽baseline120/Ruff120/RED600+15继续HELD0/1；ROOT完整联合门和预约后才可逐一使用。

新运行DB由真实fixture直接建在工作区，进程/连接真实清理后保存实际字节哈希、sidecar状态和完整索引并保留原路径。新资源/数据证据只属于新运行，不能恢复旧DB。它们不因位于工作区而获得Git交付权限。

## 实施前置与验收

ROOT先核本计划、完整输入/缺失表及所有可用原件，原生保存处置，再审核R242两作者脚本如何逐项处理缺失与持久输出。baseline在原一次槽内保存完整新27基线和精确缺失报告；不新增探针或预启动helper。

R242合法RED仍须真实poll/episode、binding及两库COMPLETE先于释放，writer真实returned且无异常，有真实正向legacy mutation，原三竞态断言精确预期失败，资源与进程完全清理。缺失历史证据不豁免任何新运行证据。任何另一个缺失、范围扩大或意外失败立即STOP交下一真实Astra。

允许ROOT完整before/CAS后仅追加planning.R245与PHASE事实，不能改写旧时点结论。旧额度不重置；R223后续四槽、GREEN9、父GREEN7、fresh12及Git0全部保持HELD。T2/T12/native/formal未完成。
