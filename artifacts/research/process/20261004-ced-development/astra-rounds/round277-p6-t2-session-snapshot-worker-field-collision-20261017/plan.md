# R277 session snapshot 字段冲突修正计划

实际模型 gpt-6-astra；仅计划，零新增运行/测试/静态/SQL/Git/review额度。

## 问题与范围

准备期插件 `session_snapshot` 先保存原生字符串 worker_id，后用 `key + "_id"` 写 worker 对象 identity，覆盖同键。不是运行失败。repository_id 不在此前字符串/primitive字段中，没有同根覆盖，保留原名。

唯一源码改动为原第150行：

```python
        snapshot["worker_object_id" if key == "worker" else "repository_id"] = id(value) if value is not None else None
```

原完整20906B/f0ed3bdd…保持物理before/base64/mode33204。单行派生后必须20953B/48e4c9da3e70ef370d0c2fb3618cdac468e0286ac23ca4d8f97c0dbbbfb7517a；其他全部字节恒等。

## 同一 consumer 绑定

尚无最终runner candidate/native，不虚构before。现有R276源码准备中，consumer只用 worker_object_id 与同PID实际资源 worker_resource_id 关联；worker_id 保留原 bounded 字符串、已有超长截断结构或null，不转换成对象identity。repository_id继续原身份语义；禁止fallback混用。无新collector、schema泛化或权限变化。

## 实施与门禁

1. ROOT全文/输入/source gate，确认原件与唯一替换。
2. 同一Sol即刻CAS旧源，先在R277持久保存完整新candidate，再唯一native Update并保全真实返回。
3. 保存after、精确diff、三字段pins报告；原R276候选/native/diff均不覆盖。
4. ROOT用原native链加本次Update逐字重构新源，核全部其他字节与mode，再审最终consumer。旧f0ed逻辑pin只经物理before/旧candidate解释，新live绑定48e4，不作路径豁免。
5. 原R276三once仍HELD0/1；全部完整source/native/input/argv门后才可预留运行。本轮不运行、不改产品/tests/observer/context/roles。

完整输入SHA、原始静态finding、精确old/new文本与物理before在plan.json和input-observation.json。出现新根因/范围/失败即停止相关工作交真实Astra；独立source准备不受影响。冻结后STOP。
