# G1 静态复位物性校验补充计划

模型 `gpt-6.2-astra`，基线 `40f9cf2d`。父计划 SHA256 `596158c29f9d43573a92c2be22a5b9db55e5d8b21f08cc8382e65e3d8b7ffb1a`。

## 首拒与归因

cvdev01 已完成一次原生 reset，0 物理步、0 命令。prospective.py:172 用字典完全相等比较复位前后物性，编译质量 0.10126432 kg 与登记/复位 0.10126431999999999 kg 相差 1.3877787807814457e−17 kg。断言先于帧导出，首槽数据库关闭为 FAILED 并释放租约；cvdev02 尚未复位。原始 stderr、首槽数据库和父登记逐件锁定。

## 最小修复与对照

只修静态采集器物性比较及本代输出绑定。复位前后精确核对原四键与形状：mass_kg 标量、principal_inertia_kg_m2 三元、body_local_center_of_mass_m 三元、inertial_quaternion_wxyz 四元；拒绝缺键、多键、广播形状、非有限值和非数值。随后逐字段使用原 g1_dual_probe.run_control 的 np.allclose(rtol=0, atol=1e−12, equal_nan=False)，逐字段记最大绝对差。保留全部其他源、身份、标定、准入及原物理属性。离线对照须接受原质量对、完全相等和零基准恰达 1e−12；用 nextafter(1e−12,+∞) 验越界拒绝，依次覆盖四字段及畸形键、形状、NaN/Inf。

## 重新采集与计数

核对输入 SHA 后用新 capture-v2 私有目录和新采集器/登记回执、独立尝试身份，绑定父登记、相同两槽及顺序、相同 130 mm XML。保留原日志的字节副本、原 FAILED 库及未发布包状态。依次原生 reset 两槽，各在 0 物理步/0 命令下采一张当场 RGB-D 与本体测量，核本槽新 frame/episode、相机、lease、状态、正常关闭和原子发布。报告一笔额外失败复位与两笔 v2 结果；若均通过，合计 3 次诊断复位、2 个包、0 次抓放和正式新增 0。新证据送父轮筛选，其余 A/B/C 工作可并行。

原始 stderr SHA256 `9f1f748d4a00472a0674a16aacec94533ebe7b401e64257cfdc212f981584cb4`；全部输入见同目录 `plan.json`。
