# R492 Astra限定计划：依赖清单完整口径

实际规划者：`gpt-6-astra`；仅规划，未实施。

**原始失败与根因：** prepare_environment.py第19行assert len(original)==70提前失败；原fla-environment.json的distributions实际71，为受保护base68+FLA2另含pip24.0（位于baseB site）。失败前无下载/overlay/模型加载。根因是把70个模型相关分发与完整可见inventory计数混为一谈，不能仅把断言改数字而忽略身份/遮蔽。

**范围：** 仅新prepare_environment_r492.py及本轮依赖清单/验证证据，旧失败脚本/日志、R491计划和固定wheel、旧71环境、产品及模型不改。新overlay仅增加原固定LMFE0.11.3/interegular0.3.3，不升级/重装pip或原包。保持严格直连、离线--no-index --no-deps、原overlay.pth明确旧FLA+baseB双site、69053-byte两wheel和全部R491范围。

**执行：** 先复核输入SHA。用PEP503规范名（小写并把连续[-_.]+归一为-，可用已存在packaging.utils.canonicalize_name）建立完整身份清单，先枚举记录再建映射；重复规范名、不同location/version、路径遮蔽不得被dict覆盖吞掉。明确三个集合：protected_model70=原base68+FLA2；incidental_preserved={pip24.0}；original_visible71为二者并集。保存来源及组别，验证集合关系/版本/location而非只有len。
新脚本沿原固定流程在干净子进程/cache cwd创建无pip的新overlay，两旧site只读.pth可见，安装两已SHA验证wheel到新site。禁止引入旧.venv-vlm。完成后必须由新overlay实际python进程读取sys.executable/sys.prefix/sys.path、importlib.metadata distributions完整记录，规范路径并检查同名重复/遮蔽；其原71项的版本及resolved metadata位置逐项等于冻结基线，且唯一新增键恰lm-format-enforcer/interegular、版本和位置只在新site，总73。不能只在父解释器md.distributions(path=...)模拟可见结果。
在新进程验证关键实际使用模块torch/transformers/compressed_tensors/fla及新增lmformatenforcer/interegular来源：不需要CUDA执行的顶层find_spec origin/search_locations先与预期site核对，真正CPU库导入时保存__file__；会触发CUDA的FLA导入按R491 GPU门槛再做，不能为统计清单偷偷触发模型/硬件。使用pip check检查整个实际可见闭包，保留freeze及原71元数据/关键源码前后hash；pip自身版本/location同样不可变。输出环境报告准确写original_visible71_unchanged、protected_model70_unchanged、new2/total73及实际新python路径，旧失败原样保留。

**验证与边界：** 一次新安装器执行与实际子进程清单验证、两wheelSHA/pipcheck和73项集合精确对照为本轮验收；不写产品测试，不加载模型。重复规范名/原包漂移/新增项非两包/位置遮蔽即停止，不删除或升级旧包使检查通过。依赖恢复不等于LMFE schema/tokenizer已通过，随后按R491原CPU门槛继续。
R491已预登记的TF convenience adapter不兼容可按既定backend-agnostic候选继续；同质prefixItems精确等价改写和已限定值keyword coverage按原计划执行。若核心schema无法支持，记录兼容性负结果/停止JSON路径；无需把每个预期负gate另当无限修复轮。新的实现根因或超出候选/keyword范围仍须Astra。

**预算前置：** 依赖/CPU原阶段截止2026-11-08T15:14:20Z，总截止16:19:20Z均不重置。本修复不增加下载额度/模型load/gen次数；若剩余阶段时间不足记录STOP_BUDGET，不能私自延时或先跑未验证环境。网络/.git需要时正常managed审批，不绕过；无GPU前置需要。独立非依赖工作可继续，原生产/71分发/venv字节不得修改。

**输入SHA：**plan.json完整固定原5项、AGENTS及failure.json的path/bytes/SHA256；实施前逐项复核。
