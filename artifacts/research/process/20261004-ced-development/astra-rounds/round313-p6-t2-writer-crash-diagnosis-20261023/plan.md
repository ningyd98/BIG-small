# R313：writer 崩溃现场保留与一次有限诊断

**实际模型：gpt-6-astra。仅规划，未执行。**

## 已知失败与未知根因

R311 writer_memory 实际 child=-11、540.657秒，wrapper c691fd exit1。timed_out/output_limited均false，父进程已回收进程组；JUnit/case/resource未完成。stderr仅有540秒超时提示、heartbeat wait、broker queue.get及截断的主线程文件名。不能据此认定RPC超时、faulthandler或codec就是根因。

父runner在JUnit不可用处停止后续index/archive，这是确证的采集顺序问题；原result仍为capture incomplete，绝不补写PASS。ROOT已把旧memory键结算SPENT，sqlite仍HELD。现场65普通文件共15230318字节及1符号链接已只读盘点，含runtime.db+wal/shm与events.db；完整SHA见input-observation。

## 先保留现场

- [ ] 对固定scene清单逐项lstat/hash，稳定字段排除atime；不跟随链接，不打开SQLite。原65文件逐字复制至本轮original-scene/files，保留mode及每个归档SHA；链接仅记原始target字节。原路径/raw/result/ledger不改。
- [ ] ROOT确认归档与原件一致、旧失败结算最终态和当前源仍适用。保留“进程组已清理，但对象资源侧车缺失”的区别。

## 一次180秒诊断

只运行原 `test_b_local_writer_requires_private_scope[memory]`，新身份 `R313.writer_memory_diagnostic` 一次，child180秒、outer300秒、cleanup15秒、0retry。原产品/fixture断言、业务时间、TTL、等待均不改；保留pytest原faulthandler_timeout=540，本次提前取得证据。

- [ ] Sol复用R311 compact runner，只改身份/单键/命令及诊断结果采集；新增小型stdlib pytest采样插件。ROOT全文复核后逐门预留，AUTHOR仍consume-before-start/SPENT。
- [ ] 每2秒一次sys._current_frames，保留有界frame文件/函数/行号以及实际CPU、墙钟、maxRSS；不读f_locals，不调用decoder/repr/product，不装profile/trace，不扫描worker历史。最多96条、每条4096字节，沿512KiB总上限。
- [ ] 采样线程自身attempt/start/normal-stop/join真实记录；每条append+fsync，崩溃缺少end就记未知。线程观察与业务资源完成不混同。
- [ ] 新runner即使JUnit缺失也独立完成流、源、basetemp/index/原DB、已有侧车、prerequisite、采样文件的保存。每个错误如实记录；不存在侧车不能推算完整资源分母。180秒终止只算诊断边界，behavior_candidate_pass永远false。

## 后续决策与限制

ROOT以重复栈位置和实际资源时间定位adopt、private inputs、公开拒绝或全量序列化阶段；进展/停留证据不能直接证明C级崩溃原因。新根因确定后另起实际Astra最小修复计划；本轮不预授权缓存、跳校验、放宽TTL或修产品。

已通过budget2及old6不复跑。旧memory不可重用；后续修复需另配有限memory行为验证。原sqlite仍保持未用，只有新世代映射与ROOT释放后才继续。fresh T2审阅、T3、P6C/native均不放行。现场与诊断仅按既有明确路径交付边界保存，DB不强制入Git，历史35DB/90sidecar缺口不抵消。
