# GPT-6.1-sol 后续派单草案：P2

状态：PREPARED_NOT_DISPATCHED。当前单写者正在完成OC2，不凭此草案开始并行改源。ROOT实际派单后实施前再次核对有限输入是否适用；既有Astra总计划技术约束完整保留。

先读AGENTS及12任务计划的接口条目2 NativeActionTiming、P2全部步骤和Global Constraints。这次只做P2动作参考与双时间域合同，不启动P3/P4或actual，不修改worker/teacher/operational窗口/三消费者，不派代理或Git操作。新问题先保存原件交ROOT→实际Astra；同一已计划的缺接口/语义RED正常继续。不要重新实验来证明旧transport反例。

先审五份现有源/测试，保留source-before；复用已批准命名反例和完整S/D单位约束，给出每动作的reference/error量、S完整horizon、未来D条件和来源提供方。NativeActionTiming只描述数据，不授资格；可算的纯数学或CPU fixture不等于真实支持。保持原UTC路径、10mm、5秒、整数D和future规则。若mutable grasp或full future D缺真实支持，按本任务计划明确UNKNOWN/NOT_SUPPORTED并停止依赖该动作的批量；不要靠v=0、隐藏误差或caller bool制造正分支。需要更换contact-completion量定义时先输出方案交ROOT/Astra，不直接扩范围。

原命名RED→最小实现→一次owned GREEN→仅相关静态→不同作者审查；新测试核语义而非重复实现。无新依赖安装、实际相机/渲染/模型/网络/物理运行。结果写t12-convergence-execution/P2/：合同、逐命令原始收据、SHA、差异、source-before/after、唯一node和状态边界；进度每关键阶段更新。已有Max成功链路不在本任务重新测试。

以下逐字继承现行任务：

### Task 2: P2 — 冻结可满足的动作参考与双时间域合同

**唯一交付/入口：** 复用现有native_references及已有transport反例；无actual、无九组批量。

**依赖：** 无；可独立开始

**Files:**
- `MODIFY src/cloud_edge_robot_arm/vision/native_references.py`
- `MODIFY src/cloud_edge_robot_arm/vision/native_calibration.py`
- `MODIFY src/cloud_edge_robot_arm/research/native_geometry_calibration.py`
- `MODIFY tests/test_native_references.py`
- `MODIFY tests/test_native_calibration_source.py`
- `NEW artifacts/research/process/20261004-ced-development/t12-convergence-execution/P2/contract.md`

**Interfaces:** 采用上文NativeActionTiming；现有resolve_native_reference签名保持。固定世界TCP参考与OBJECT_CONTACT分别登记支持范围；原UTC注册不改语义。

- [ ] **Step 1:** 复用test_actual_transport_displacement_cannot_meet_original_total_motion_gate，写精确合同表：每技能参考、几何误差量、运动量、完整S horizon、future D要求、生产者、三消费者、不可支持理由。
- [ ] **Step 2:** 新增test_fixed_goal_zero_reference_velocity_is_not_zero_body_velocity：只有重算相同payload和完整source证明固定世界endpoint时reference速度可0；实际body移动不因此拒绝，tracking/holding仍须独立界。新增test_mutable_grasp_reference_without_future_support_remains_unknown：mutable contact没有future支持不能得到finite/0。
- [ ] **Step 3:** 新增test_native_timing_never_multiplies_sim_speed_by_wall_age：S age2/H3/v.001/e.004得到.009；D TTL独立5秒允许、5秒+1ns拒绝。新增test_full_future_wall_bound_missing_is_unknown_when_required：sim timeout或过去均值不能填future_wall_bound_ns。
- [ ] **Step 4:** 运行命名RED后最小补齐类型/注册语义；原已有transport反例只作为回归，不重新声称RED。将GRASP动态参考和完整未来D的支持路径作可行性判定：有真实来源可支持才列SUPPORTED；没有则明确NOT_SUPPORTED并在这里停止依赖该动作的批量。
- [ ] **Step 5:** 若需从原OBJECT_CONTACT速度模型改为吸收target drift的全horizon contact-completion误差，先单独输出版本化量定义/校准设计交root审查；该语义尚不在本计划直接实施授权内，须下一Astra限定补充，不用e中藏误差或v=0临时过门。

**验证/实际命令：**
```bash
.venv/bin/python -m pytest -q tests/test_native_references.py tests/test_native_calibration_source.py -k "transport_displacement or fixed_goal_zero or mutable_grasp or native_timing or full_future_wall"
```

**验收出口：** 合同表每个受支持动作都具有原10mm与完整horizon下可到达正分支；不支持动作明确UNKNOWN。这是可行性出口，不宣称已有校准值。

**失败停点：** 若完整抓放关键动作没有支持路径，停止九组/大先导，报告具体数学或来源缺项；不能靠加样本修不可达合同。

- [ ] **交付：** 保存本任务局部报告、原始命令/退出码/完整stdout-stderr、输入输出SHA与actual分母；按下述显式路径Git规程提交。
