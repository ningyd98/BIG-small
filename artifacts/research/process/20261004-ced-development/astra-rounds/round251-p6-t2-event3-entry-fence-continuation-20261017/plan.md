# R251 — event3 真实入口围栏续修

实际作者 `/root/astra_status_plan`；实际模型 `gpt-6-astra`；2026-10-17。仅计划，冻结后 STOP，待 ROOT 门控后由唯一 Sol 实施。

R248 已由 ROOT e4373a（exit0，4168 项）结算为合法 RED：三个原节点在 late-local-binding 原断言失败；真实 private bootstrap/binding、两库 COMPLETE 之后，writer 返回且正向 legacy RUNNING 写入可见。没有超时或观察错误。927 次资源尝试／924 初始化／927 清理只属于该次实际观察。

根因仍是 R223 原问题：public wrapper 在真实锁内检查后释放锁，再调用会重新加锁的 original，binding 可在空隙提交。SQLite 第二连接要求 binding 复查与写入处于同一实际写事务，单实例 Python 锁不够。

## 源码边界

只允许 protocol.py、memory.py、sqlite.py 三文件。加入 `_local_legacy_write_guard_unlocked(repository, name, args, kwargs) -> None`，在调用者已有实际锁／SQLite 写事务内重新执行原 `_local_target`；local 则按原 private operational scope 规则拒绝。helper 不加锁、不提交、不注册权限、不缓存负查询。

Memory 的原 36 writer 在实际 Lock 内、首个写入或影响写入的读之前围栏；原 mark_event_handled 仅为既有 membership 返回补真实 Lock+围栏。SQLite 的原 36 writer 在真实 `_write_lock` 与一次 BEGIN IMMEDIATE 内围栏；复用现有 BEGIN，隐式事务入口补 context/BEGIN，异常和提前返回完成或回滚事务。保留业务 SQL、参数、CAS、幂等及 commit 所有权；delegates 不重复 BEGIN。完整 72 项源清单必须逐项给出参数映射／锁／事务／首效应／围栏位置。

私有 registered-scope 分支保持；精确已有 positional CANCELLED 路由保持。原本 unbound、随后失去竞态的 fallback 可 fail closed，不能扩大取消参数或权限。冻结 fixture16525/106fde、其他24源、原 observer、211保护、时间／预算／TTL 和全部旧脚本均不改。

## 原额度接续，不新增槽

真实 R223 prepare_red/red 已 spent，仍保留其非合法启动失败。仅续用剩余四个身份：prepare_green120、Ruff120、GREEN9 600+15、ROOT settlement120，各一次，无重试。R251 ledger-links 只引用原额度，不复制第二套额度。ROOT fullbefore/CAS 后只更新四个未用入口的 continuation，原已消费记录不改。

新脚本及所有输出位于本轮。精确 argv/env/cwd 在 plan.json.commands。GREEN 为原九个节点，沿已验 R235 import-only 前置和当前106fde夹具；basetemp 在 workspace 新持久路径。Ruff 仍一次 E9/F63/F7/F82，明确涵盖三产品、冻结夹具与三个新元数据脚本；不增加批次。旧 R223/R232/R248 脚本不覆盖、不重跑。ROOT 独占新 stdlib settler。

实施顺序：ROOT 计划/输入门 → SoleSol 三文件最小修复及72项diff清单、两作者脚本 → ROOT 准备settler并全文源门 → 原prepare_green一次 → ROOT接受 → 原Ruff一次 → ROOT接受 → 原GREEN9一次 → ROOT原settlement一次。每步 ROOT 先预留再发 literal，未预留不得启动。无新RED/collector/探针。

## 数据与世代

输入观察769156 B，SHA256 `21b9337e50edee0d62d4d22abeb6606ff31be3dec5e325dd9d4e91f7117f76c5`。正常规划核查659项全true，379实际pins；完整三源 before/base64 和两原角色 before 已保存。该元数据读取不算产品验证。

R248 最新 source-index 为3239196 B／`e204ace1b81a6f012bc176158c6b16c5e5d0f0538618299ff53d2dff45aa040e`：27源、211保护、3scripts、1223 history observations、26精确maps、32 inputs。严格按真实schema，不套旧 history321。新增仅目标三源完整before映射、R248最终七before映射以及明确角色/CAS代次；不递归扩表、不按路径笼统跳过。固定身份只比较 path/bytes/sha256。

原35项缺失保持逐项隔离、hash/bytes不伪造，90旧sidecar缺失状态单独保留。R242+R248 当前12个workspace DB及36sidecar严格逐步前后核验，不能套用缺失例外。新GREEN数据持久保全，只证明新运行；不恢复旧数据库或远端复现包。STATE/PHASE 当前快照在观察中，后续只可 fullbefore/CAS 后追加 planning.R251/PHASE 事实。

## 验收

GREEN 必须9PASS／0FAIL／0ERROR／0SKIP：竞态3拒绝晚到writer并不产生legacy变化；先写后绑定2真实允许；bound取消2和unbound legacy2保留。完整记录真实双COMPLETE、线程/连接身份、资源分母、finally清理、hook恢复和退出；不能以wrapper0、固定历史资源数或源码72项代替行为证据。

任何错误、超时、源漂移、额外缺失、清理失败均消费实际槽并STOP。ROOT新结算必须区分原失败链、R248合法RED和当前GREEN源代，不借旧settler假定以前RED合法。

最终即使本围栏的软件证据通过，也不代表完整T2；父GREEN7、freshreview12×600仍另门，T3/B9/T12/native/formal/Git均未放行。详细合同和完整pin索引见 plan.json 与 input-observation.json。
