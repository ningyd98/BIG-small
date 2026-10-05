# 第52步：逐数组诊断与真实步号核验修复

本步完成一次有界真实诊断、原始字节独审和新版本离线核验器。真实诊断退出1，仍为 PARTIAL/FAILED；完整教师动作采集、独立校准和 native 准入均未取得。主线仍 T12/18、T13 并行，边缘模型型号后置。

唯一新诊断执行10个被动物理步，11次实时额外采集全部保存，0次实时采集失败；setup/bootstrap各1次，总camera调用13次，0教师动作、0运动命令、0模型请求、0硬件调用。末尾仅尝试一次 copy，原 live hash guard 抛错，未发布 validated/rejected 事件，clone camera调用0。不能以 `copy_rejected=0` 解释为复制通过，也未重跑或续跑旧试验。原试验11次/10保存/1失败及未完成的120步 settling 分母保持原样。

[完整原始清单](diagnostic-1-file-hashes.json)含142文件、7,876,865字节；137个gzip包括101份数组快照、22份render数组、13份观测和1份journal。summary的123个snapshot payload是101快照加22 render数组。独审逐一重算101×154个成员与aggregate，33个render phase均无变化，33份执行来源/441,826字节、19个安装依赖 pins、旧23个已存文件和7个父级保护件均匹配。见[独立复核](actual-independent-review.md)和[原始分析](actual-analysis-1/report.md)。

step0在渲染前重复读取仅五个 island getter 的新 owning 数组字节不同；末尾 copy 前后仅两个 owning efc_AR getter 不同，其余真实data-backed数组及保护成分相同。版本化绑定、pybind和NumPy API支持“读取分配的字节造成假阳性”这一限定解释；原始拓扑未保存 native C pointer，NumPy运行版本与取得的2.3文档、绑定ABI与精确patch来源仍有限制。因此该解释只适用于本诊断的具名读取差异，不证明旧缺失帧的具名原因、全部native C状态或detached采集安全；冻结guard与原始报告均未修改。[版本化来源及限制](actual-analysis-1/report.md)。

[新核验器](../t7b-continuous-visibility-v2/verify_offline.py)按真实ACTUATOR upcoming步n关联CONTROL/PHYSICS BEGIN n−1和PHYSICS END/frame n；明确只读输入及树外全新输出。17项CPU与root独立17项通过（同套范围不相加）。原失败试验重放退出1：11allocated/10verified/1failed，九条假错关联消失，六条真实失败保留。原核验器、来源、header、原始数据与旧审查未改写；root三个辅助审计fixture错误另存，不当作物理试次。见[核验器独审](../t7b-continuous-visibility-v2/independent-review.md)。

新诊断11帧的离线OpenCV解码为11 OBSERVED，仅覆盖0至0.041666667秒的被动前缀；真实诊断decoder调用0，之后离线调用11，二者分列。与旧成功前缀十步的窄物理hash和sim time一致也不补回旧缺失帧。见[离线解码](passive-prefix-pose-decoding.json)与[十步比较](successful-prefix-comparison.json)。

native Task2 的组件名碰撞已在独立算术复核中关闭（34项范围），来源/预注册 chronology、完整horizon及policy适用性仍在修复，活动源码不在本步Git交付。新状态guard正在按完整动态getter合同实现，尚未集成或真实运行。本步交付限定为冻结诊断、v2核验器及本阶段报告；历史批量原始材料的远端可移植归档仍未全部完成。

下一步完成新guard的独审与新协议完整教师horizon采集；并取得真正的原始生产者、独立reset/UTC来源和校准组后再激活native消费者。外部UTC误差、几何/动作误差、contact/future来源仍UNAVAILABLE；Max、风险、机会/200故障、合格B0及INITIAL/METHOD/FINAL仍未验收，formal_accepted=false。

提交前定向验证：诊断31项与v2核验器17项在独立导入模式下合并48 passed（1.17秒），四个源/测试Ruff通过，修改文档差异检查通过。首次默认pytest导入因两个 `test_cpu.py` 同名而收集失败（0项运行），原日志保留；未删除cache或改源，修正命令后通过。见[原收集日志](../validation-step52.log)与[48项日志](../validation-step52-importlib.log)。独立同套验证不额外累加，未运行全仓套件或新物理试次。
