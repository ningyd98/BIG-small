# V2 离线核验器独立审查

结论：PASS_SCOPED。Root独立17项CPU通过（1.09秒），重新离线重放原失败试验，CLI按预期退出1。旧试验仍11allocated/10verified/1failed，九条ACTUATOR步号假错关联消失，六条真实缺项完整保留；未调用decoder、renderer、physics、provider或hardware。

Root核对修正来自真实_backend._build_actuator_observation的total_physics_steps+1：frame/PHYSICS END是n，CONTROL与PHYSICS BEGIN是n−1，ACTUATOR是即将执行的n。四个原frame/hash/camera/clock helper AST完全相同。verify_attempt的必要差异仅是明确输入/新输出目录、UTF-8独立gzip helper、upcoming n lookup和版本元数据；原saved-END、终episode/time、half-open command/action/unique owner以及顺序/时间括号约束保留。输出必须在输入树外的全新目录。

原32执行源码及原21采集文件hash复核不变；未回写旧核验器、header、attempt或旧审核。Root两次AST辅助核查假设错误和一次报告字段名错误另保存，不计生产失败或新增物理试次。已保存独立完整replay输出与测试原log。

当前source authenticity UNKNOWN、外部UTC/error/future来源UNAVAILABLE、native NOT_PROMOTED、continuous NOT_CERTIFIED、formal=false。此核验器不授予实际native/calibration/source权限，也没有取得完整动作horizon。
