# R451 — 真实背景实例 sentinel 与 reader schema

实际 gpt-6-astra；2026-11-08；只规划，0产品修改/测试/physics/render/model。

原始证据：R439 implementation/whole-change-review.md/json 的 F1，ROOT接受；camera.py 实际将非geom像素保存为 -1，instance_labels遍历 set(instance_ids)-{-1}，而新reader.frame要求全部ID有label。旧软件camera人为给-1标签，掩盖不兼容。27份原始输入及SHA在inputs.json，逐字副本intake；R451/R452/R453已在ROOT改动前一次冻结同一baseline，后续不重采覆盖。

范围仅新reader、tests/test_native_instance_originals.py 和新共享CPU fixture tests/native_collection_source_graph.py。reader保留原instances.i32字节、label映射、pass/physics/checksum/库存验证，仅改实例语义为：ID -1是已知背景sentinel，不要求或合成标签；所有ID必须>=-1；每个非负ID必须在原label映射中。不要修改旧camera/backend/RawV3或旧通用fixture，也不添加默认background标签。

共享fixture使用现有软件backend加NativeFullHorizonRecorder的真实callback/streaming/RawV3数据形状；仅替换实际物理引擎与render为显式SOFTWARE_ONLY内存数据。新fixture局部camera返回混合(-1,合法geomID)与仅非负label，注册camera原字段一致、2pass空instances与3pass全instances、state/pass/hash关系完整。不得mock reader.frame、metadata验证或把bare字典标成完整actual。可以用旧source_recorder搭建，但在新helper中覆盖局部camera返回，禁止改旧helper语义。新helper只服务本三轮CPU测试；缺full-H/owner证明仍UNKNOWN。

两个精确节点与展开spec见plan.json：第一节点通过真实recorder写出背景及非背景像素，_Audit.frame读原件成功且未添加-1label；第二节点从该原图删除一个非背景label（重新生成对应软件库存，以验证语义而非仅hash），必须报instance label缺失。并检查未知负ID不得获准；若该额外负ID断言会引入第二个RED，放在GREEN阶段首节点内部而不变原RED选择。原字节和原fixturebaseline另存，不覆盖历史研究原件。

唯一instance-red：预期1FAIL（当前要求-1label）+1PASS（非背景缺label仍拒绝），不得import崩溃。修复后唯一instance-green：2PASS。每阶段child120s/outer240s、fresh目录/basetemp、R413监督/r413_events/r235 prerequisite，0actual。原F1静态发现已作为失败证据；无额外probe/collect-only。静态统一在R453最终受影响gate一次执行，避免每根因重复扫描。

实施前重验本27pins。完成后生成implementation/step-report与精确前后SHA/diff。后续R453将看到reader和共享fixture的已批准漂移，必须用该报告和原intake复核适用性，写新applicability.json，不覆盖原pins。若其他变化/失败则暂停交Astra；不能扩大本轮为控制或guard修复。

验收只代表F1 CPU来源schema一致，实际full仍NOT_RUN、nativeUNKNOWN。F2/F5由R452，F3/F4由R453；全部通过和原reviewer scoped修复复核后才考虑原prepare/full/read。R450服务授权完全独立，首组预算不变。
