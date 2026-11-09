# R517 Metadata resolver lazy factory Implementation Plan

> **For agentic workers:** 使用 superpowers:executing-plans。实际规划模型 gpt-6-astra；用户已授权限定接口修复，无需再次确认。仅规划，尚未修改resolver或恢复下载。

**Goal:** 修正MetadataProvider.find_matches返回协议，避免resolvelib急切获取全部历史版本metadata，并保留完整排序/约束/回溯语义。

**Architecture:** 将已有内部generator函数本身作为factory交给resolvelib；仅直接postoverride消费者显式调用factory。当前pip vendored build_iter_view对callable使用_FactoryIterableView，其余非Sequence调用list(matches)，因此问题是返回接口而非候选算法。

**Tech Stack:** 现有.venv Python3.12、pip._vendor.resolvelib、原metadata-only provider；不升级依赖。

**Spec:** 本目录failure.json和R515计划；R515官方服务栈锁定与物理下载/离线安装界限保持。

## 原始问题、证据与核验

failure.json source SHA203ddf5ddf458d663c9eb9463ac2a969815db459cbfe7f553fcd8c431b8d677f已核验。原resolve-download.stdout列出大量setuptools与wheel历史版本，末尾已到wheel0.8；stderr保留KeyboardInterrupt。父任务已SIGINT停止自有PID3502320，未产出完成lock、未安装/模型加载/生成，不能将中止当依赖解析成功。

本规划读取当前.venv的pip/_vendor/resolvelib/structs.py并记录SHA，确认build_iter_view首先判断callable；否则非Sequence materialize list。现find_matches返回candidates()为generator，导致metadata网络读取在首次构造view时穷尽历史候选。_FactoryIterableView通过itertools.tee支持重复迭代，不要求改候选迭代内容。

inputs列原日志、源文件、R515计划与实际接口源码SHA。原日志和已下载metadata必须原样保留，不重新抓取覆盖已有字节。

## 限定改动与不变量

唯一运行代码改动为R515 implementation/resolve_official_wheels.py两处：

1. MetadataProvider.find_matches尾部 `return candidates()` 改为 `return candidates`。
2. main中官方cuDNN postoverride直接consumer改为 `list(provider.find_matches(... )())[0]`，仅增加factory调用，保持其原有list/首项语义。

不改versions枚举、逆序排序、Requirement/marker/extras/Requires-Python、candidate不兼容集合、wheel tag/yanked过滤、details缓存、副作用时机以外的选择逻辑、网络policy/hosts/超时/hash校验、线程数、resolver max_rounds或官方版本。不得给版本数设置上限、跳过历史候选、pin新版本、改成另一resolver、优化其他路径或升级pip。lazy仍允许真实回溯按需请求旧版本，不能以“访问了多个版本”单独判失败。

允许R517 tests/test_lazy_factory.py、diagnostic/旧source副本/RED-GREEN/metadata缓存清单、step-report.md；允许R515 diagnostic/resolve-download-02.stdout/stderr/exitcode及后续原计划尚未存在的metadata-lock/wheelhouse-lock。旧resolve-download.*不可覆盖，旧source副本精确保存为R517 diagnostic/resolve_official_wheels.before.py并核原SHA。

## 前置条件

实施前重核所有输入SHA、确认旧PID确已结束且没有另一相同resolver运行。枚举现有META/*.raw.json路径/bytes/SHA到本轮缓存快照；只核读，不删除或重写。metadata-lock.json/wheelhouse-lock.json若已存在先判定已有运行状态，不覆盖或另开并发运行。

使用与已核structs相同.venv解释器；若实际接口源码变更或其他find_matches direct consumer出现新契约，先停止重新分析。测试必须无网络/无下载/无模型，实例化provider时避免其__init__真实HTTP setup，采用__new__加合成sources/cache/details/get，测试实际find_matches方法和实际build_iter_view。

## Task 1 — 精确RED/GREEN

- [ ] 保存原source副本与缓存快照。新增合成provider，三个满足条件且有兼容wheel的版本3.0、2.0、1.0；get计数区分项目releases metadata与单版本metadata，最新版本可直接满足。用真实build_iter_view构造视图并next(iter(view))，断言只取3.0的单版本metadata，未取2.0/1.0。当前代码预期会获取全部三个，保存RED原始命令、输出和退出码。
- [ ] 附加测试：factory是callable；仅find_matches和构造view不应获取单版本metadata（允许一次project releases读取）；首项后重复iter/view或bool(view)不强迫遍历全部；显式读取下一项才取下一版本，排序仍3/2/1。全部遍历的候选列表与旧实现合成结果完全一致，不能把懒加载变成漏候选。
- [ ] 测试真实Resolver遇到最高版本的合成依赖冲突时仍能回溯下一兼容候选；只断言最终版本/依赖语义与预期相符及按需求访问，不锁内部实现细节。检查固定postoverride消费者使用find_matches(...)()后得到9.16.0.29、details已填；通过实际consumer AST或提取其表达式测试，避免只测测试代码自造调用。
- [ ] 实施两处限定改动。执行 `.venv/bin/python -m pytest <R517>/tests/test_lazy_factory.py -q`，要求全部GREEN，保留日志。审查diff只有上述两处；无需联网或全依赖下载来证明单元回归。

## Task 2 — 复用缓存恢复原授权准备

- [ ] 核现有metadata缓存每项SHA不变，provider.get已有文件读取路径保持。独占新建resolve-download-02.stdout/stderr，记录实际命令、解释器、PID和结束退出码；只启动一次修复后脚本，不复活原PID或并发同wheelhouse。
- [ ] 沿R515原授权继续metadata解析及原hash校验物理下载；旧缓存直接读取，新增metadata独占写入，原下载wheel复用仍核bytes/SHA。不以计划外版本限制人为加速，不清理旧metadata。
- [ ] 运行早期观察按需版本读取与进度；没有固定“只能读一个版本”的真实网络门槛，因为依赖回溯/无兼容wheel会合法读取更多。若再次无进度，先保留日志定位证据；不得把新的性能/接口根因自动并入本轮继续修。
- [ ] 完成后metadata-lock和wheelhouse-lock应由原脚本独占写入，后续R515离线pip resolver仍是独立验收，不能把自建metadata solver结果冒充pip安装验证。复核旧缓存和失败日志SHA完全不变，记录新增文件清单。
- [ ] 写R517 step-report并汇入阶段总结，区分软件RED/GREEN、metadata/download实际结果、尚未执行安装/GPU。沿既有显式研发交付提交推送并核三方SHA，缓存和wheel仍本地不进Git。

## 验收与停止边界

本轮通过为两处接口修复、合成lazy与回溯测试通过、旧缓存/日志未改；真实解析/下载状态单列，不因修复代码通过宣称闭包已完成。安装和模型调用不属于本轮修复验证，仍由R515/R513后续门禁控制。

新provider接口异常、真实resolution无解、metadata/hash不一致、网络新失败或需修改候选/依赖规则时停止受影响修复并交新实际Astra。预期RED的急切枚举是已批准根因，无需另轮；其他失败不在此授权中。规划阶段未实施两行改动，也未恢复进程。
