# R307：按提交阶段核对 detached job summary

实际模型：**gpt-6-astra**。仅规划，未实施或测试。

## 原失败及判断

R306真实dual运行47.997秒，capture完整、9事件0丢弃、410资源全部清理。首个event/PENDING真实COMMIT后关闭已成功产生ProgrammingError，独立event行1、job行0，both_complete=false；失败在重启后helper要求job summary必须包含该operation_id。原9.9MB true-commit-loss.json及完整失败已固定SHA，ROOT已结算SPENT。

job.read_local_publication只查job表。首个event提交先于任何job回执，正确summary不能包含此目标。原helper还使用整段JSON子串搜索，无法区分顶层operation_id与嵌套文本。根因是测试预期与阶段矛盾；产品无需修改。

## 精确修复与全部调用核对

仅修改 `_b_t2_detached_read` 和原dual内两个调用及必要的独立读取/证据字段。增加必填keyword-only `expected_job_phase`、`expected_job_rows`。summary按具体API要求list/dict；只按顶层operation_id精确选取目标，且与独立SQL读取的目标行逐字段一致。

| 场景 | job目标数量 | job phase |
|---|---:|---|
| event/PENDING | 0 | None |
| job/EVENT_COMMITTED | 1 | EVENT_COMMITTED |
| event/COMPLETE | 1 | EVENT_COMMITTED |
| job/COMPLETE | 1 | COMPLETE |
| same-live-owner | 1 | COMPLETE |

None必须证明目标行真正不存在；不能要求整个summary为空，因为先前setup操作仍可存在。其余阶段必须恰1行，不接受重复、错误phase或SQL不一致。

所有summary行保留严格HISTORICAL_ONLY、UNKNOWN、accepted=false、live_authority=false；保留递归禁止NEW_COMMIT/授权标记及修改副本后重新读取一致。重启仍必须拒绝无private authority的transition，预算与原始来源不变。记录固定expected phase和独立before rows；重启这些只读路径前后目标job rows须不变。

本席位已审阅全部两个调用、四处提交顺序及job主键/读取/reconcile实现。事件COMPLETE到jobCOMPLETE之间job仍EVENT_COMMITTED；same-owner的COMPLETE也只提供历史证据。不得以删除历史检查、跳过首例或根据当前输出猜phase解决。

## 验证和额度

现有实际失败作基线，不重跑48秒RED，不重标旧legal_RED。新增一个冻结micro测试调用实际helper，以只读double覆盖五种phase、嵌套/前缀ID不能假匹配、缺失/重复/错误phase/字段不符/授权标记均拒绝和副本隔离；double不充当行为证据。

新R307 micro一次120/240秒，随后新dual一次600/900秒，均0retry。复制已经实际验证的R306简明runner/plugin，仅改身份、两个key与新fixture SHA；保留512KiB总容量及原393216/131072分配，不能再次串联替换容量数字。原R306两个key永久spent。

dual必须实际完成全部4处COMMIT-loss/4次重启和same-owner完整断言。通过后接续原R302两个仍HELD0/1的wait，不新增wait身份：按完整before归档/CAS推进原操作gate/acceptance，仅映射原产品9b94→已接受G2产品与原fixturea280→本轮G3，其他原命令/runner/plugin保持；原wait不加载被动plugin。ROOT独立审阅后依次reserve并执行原literal wait命令。

## 来源、交付与停止

G1选择性观察器、G2一行产品修复、已有micro源码和所有旧失败原件均不改。新fixture diff只允许helper、两个调用及明确证据字段。输入SHA和ROOT新结算实物见plan.json/input-observation.json，不重审68历史或重跑旧gate。

验收仍要求完整raw/JUnit/实际资源清理、源码前后pins、0drop/hook恢复、真实DB归档、所有原安全与预算断言。下一个实际失败保留后再交Astra，不自动扩大范围或重试旧槽。链路闭合后ROOT按授权明确路径提交推送；不晋升整个T2/P6/T12/native/formal，原35DB/90sidecar缺口保持。
