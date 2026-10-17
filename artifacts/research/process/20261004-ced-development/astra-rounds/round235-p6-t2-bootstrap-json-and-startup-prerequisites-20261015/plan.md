# R235：本地描述数据 JSON 边界与启动依赖前置

实际作者 `/root/astra_status_plan`，实际模型 `gpt-6-astra`。仅规划；ROOT 完整门控后由原唯一 Sol 实施。

## 已证问题与边界

R234 两个 SQLite 用例真实异常为 `detached JSON data required; live objects are forbidden`，链路指向 runtime._local_envelope 对 original_time 的严格复制。P5 OperationalDomain.namespace_offsets 明确为嵌套 tuple；asdict 保留 tuple，runtime original 的 app_domain 和导出 reference.domain 均带该非 JSON 容器。后继 _check_local_locked 的 app_domain/app_current.domain/app_references 也存在同根因静态缺口，尚未执行到。

仅修两个生产者：`worker_runtime.py::_initialize_local` 在原件注册前用既有 `_descriptor_plain` 脱离新建完整 original mapping；`operational_windows.py::_check_local_locked` 在原有严格 LocalAuthorityDecision.from_payload 前脱离完整决策输入。所有字段/来源/权限/当前时钟检查保持；strict codec、P5、broker、export_record旧行为、旧测试/观察器/event3均不改。

Memory 根因仍 unknown。真实CPU clock_factory 在 broker/profile 区域首次通过 _Counter 导入 tests.test_operational_time_v1。已核该模块只有导入、定义和pytest参数元数据，没有顶层 identity/clock调用。本轮显式把这一个原依赖模块导入放到新子进程 pytest_configure、原测试分配前；这不是产品预热、时钟重采或已证明的超时修复。不得增加wait/TTL或修改线程权限。

## 输入与范围

完整输入索引 `input-observation.json`：85005 bytes，SHA256 `8d4883ea876fb494382bf4d37e7a1c71e154a76841b853113129071e90702fc9`。含三原始trace、27物理源对、211保护实际pin、旧角色/raw、6旧DB和18旁文件缺失证据。R234所有原件保留；其3FAIL只属诊断，不是legal RED。

唯一Sol仅修改上述两个函数边界，并新写本轮 prepare-evidence.py、run-command.py、r235_startup_prerequisite.py。完整before/CAS、精确diff、非允许函数字节不变、原27与新27世代分开。ROOT必须全文读三新源及插件准确导入合同，不能先执行import/probe自查。

## 有限新验证

三个独立once槽，初始全HELD，无重试：baseline120s → 两产品源窄Ruff120s → 原3节点恢复RED600s/cleanup15s。精确argv、cwd、有限env与独立证据路径见JSON。新RED使用新basetemp及本轮目录，不重用任何旧结果/预算。

插件只导入已pin原依赖一次，不reload，不调用identity/clock/worker/fixture；保存真实module路径/SHA、sys.modules前后、耗时及profile/trace不变证据。模块已载入时如实记录。源审核禁止直接factory调用不冒充运行时穷举零资源测量。任何导入异常或漂移即保全停止。

baseline保存完整候选27/211、脚本/角色/旧raw/DB不变和两函数差分证明。RED必须先保存全部JUnit/case/resource/清理原件，再计算接受状态。必须实际3FAIL均为原竞态断言，同时三例达到真实bootstrap、binding及job/event双COMPLETE；预导入成功、wrapper退出码、任意3失败均不能代替。

资源分母只本次真实观察；保留构造/初始化/never-polled/poll/cleanup分开，未观察的partial broker和OS/native仍unknown。所有真正wait/clock/TTL不动。stdout≤6000 UTF-8 bytes，独立完整raw/JUnit及工具对象即时store。

## 历史与后续

R223/R232失败槽永久spent；R233/234诊断槽spent。原R223余4、父GREEN7及审查/Git额度不释放不reset。即便R235合法RED，也先STOP；下一真实Astra continuation须明确新baseline、GREEN9/父GREEN7需要的同一导入前提、有效新runner/argv和多代结算。不得假称旧runner自动具备前提，不执行旧失效settler或将新结果塞旧路径。

ROOT只可记录本轮角色/证据/步骤与full-before+CAS事实checkpoint，不能升级阶段验收。实际行为修复须由真实bootstrap路径证明；Memory根因若仍不明如实unknown。T2/T12/native/formal/Git交付均未完成。
