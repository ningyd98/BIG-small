# R488 Astra限定计划：标准JSON原生子类与可靠失败证据

实际规划者：`gpt-6-astra`；仅规划。已做不含模型的CPU类型读取以核验根因，未实施修复。

## 失败与核实根因

R487 loader及zero missing/mismatch、248FP8/GPU/BF16 inventory已通过，尚0请求。主失败为保存model.config.to_dict()中/quantization_config/quantization_status QuantizationStatus，finally又因state的/torch TorchVersion写失败掩盖主异常。实际Astra只读CPU检查已证实二者均isinstance(str)，stdlib json分别编码"compressed"、"2.10.0+cu128"；原codec exact type判断误拒绝合法原生子类。旧set修复已工作，此轮不撤销；未知其他类型仍须在CPU前检，不默认宽松放行。

## 限定范围

仅新evidence_codec_r488.py、experiment_r488.py、run_profiles_r488.py、score_profiles_r488.py及CPU预检/报告。codec修原生子类语义，runner只改新helper/唯一raw-result路径及不会掩盖主异常的最终日志；scorer只更换helper与明确新输入。旧脚本/原protocol/raw/log/partial/失败结果只读冻结，模型内存/权重/量化/attention、输入prompt/图像/生成参数不变，base68不动。FLA已安装overlay状态不改，独立CPU import/processor门槛仅在旧失败日志冻结后可继续。

## 编码契约

按stdlib JSON原生语义接纳isinstance(str/int/float/bool/None)及dict/list/tuple原生容器子类，而非只接纳type完全相等；bool优先识别，保持整数/浮点/字符串原生编码值，不能用str(value)处理字符串Enum（可能变成枚举名）、不能用default=str/宽泛repr。纯Enum/任意对象/非原生Mapping或Sequence未经标准JSON支持仍拒绝。dict键遵守stdlib skipkeys=False支持范围及转换语义，不默默跳键。原生scalar可原样交stdlib encoder；容器递归规范化保留内容，所有非builtin原生子类处理在sidecar记录qualified type、JSON Pointer/键位置、原生基类及处理规则。set/frozenset继续确定性canonical排序数组并标注。全部路径保持输入不变、循环引用检测、allow_nan=False，未知对象/NaN/Inf仍失败。完成编码后exclusive-create新输出，任何旧文件不覆盖。

## 重新加载前CPU门槛

复核全部输入SHA及新旧源码最小diff，先完成不load权重、不建GPU模型的CPU门槛：实际torch.__version__、实际QuantizationStatus.COMPRESSED、torch/CT声明的其余实际enum状态；native scalar及dict/list/tuple子类、IntEnum、set/frozenset空/非空/嵌套、含实际loader字段结构、非法自定义对象、循环和NaN/Inf。对无set的标准JSON支持fixture与stdlib json.loads(json.dumps(...,allow_nan=False))结果逐项相等，sidecar路径准确，原对象未变，未知类型仍拒绝。
按实际runner在第一次generate前的所有save调用列一张覆盖表：运行state（包含真实TorchVersion）、adapter config、loading info、initial inventory、model-config、generation-config、processor证据等。使用既有prepare/AutoConfig/CompressedTensorsConfig.from_dict与GenerationConfig.from_pretrained等无权重构造取得真实对象/字典；加载与inventory的已冻结实际返回证据可作为historical fixture，明确不是新loader数据。使用真实processor双图CPU预检得到特征证据。每项都实际经过新codec编码/sidecar生成并roundtrip；不能只测两个简化字符串后再次靠模型发现错误。配置来源与key集需对应真实load使用者；无法CPU取得的动态项列明实际类型来源/覆盖边界，不伪造已测。

## 主异常保留

runner捕获首个运行异常时立即保存不可覆盖的primary-stage/type/message/完整traceback文本及当前requests计数到简单文本证据，保留原异常用于最终返回。finally先确保采样器/本轮GPU锁等原清理照常执行；最终state序列化用独立try，失败时另写secondary-evidence-error文本，并在stderr显示主次两份，不抛secondary覆盖primary，不将状态改成成功。文本紧急日志不依赖复杂JSON codec。若无primary但最终证据保存失败，报告EVIDENCE_WRITE_FAILED/非零退出；不能吞错误。CPU故障注入验证primary+secondary同时存在时两者保留且主错误优先；仅为日志helper验证，不执行模型。

## 真实执行与预算

全部CPU门槛通过后，一次替代A加载运行同一ON,OFF,OFF,ON,ON,OFF,OFF,ON，使用唯一run-base-r488 raw/result；FLA随后若所有门槛通过用唯一run-fla-r488运行相同8次。原90分钟从约13:09UTC起算不重置（截止约14:39UTC，实施者按实际保存起点精确核对）；修复/CPU门槛<=8分钟。显式把本轮最大load上限增至4：两次历史证据失败后loader返回+A一次+B至多一次；最多生成仍16、零额外warmup，load600秒/每请求180秒/GPU>=14000MiB共享锁无offload不变。再遇新未知编码/模型/processor根因立即保留异常并新Astra，不继续放宽encoder。


新增独立负门槛：FLA processor输入/函数选择PASS并不覆盖实际Triton就绪；其stderr已报告缺Python.h导致cuda_utils编译失败及fallback CPU警告。因此当前B硬件就绪=FAIL，R488不得运行B；可按R486原预期门槛标B_NOT_RUN并优先完成A。R488不授权补headers/装编译器或任何系统修改；若要修该不同根因，必须另行Astra限定计划且仍受原90分钟预算。

## 交付依赖决定

本轮新研发交付采用已推8b4a88bde7de996a44a119115dc2f735bdad5807作为明确父commit，保证R473-R484已交付helper可作祖先；R485按其既有约定为本地post-commit审计，不误称已在该commit。仅追加R486-R488明确artifact路径（后续轮若出现须再明确），共享research HEAD e244076...不checkout/重置，不加入无关产品更改。执行数据的source hash仍取本次live inputreview，不为了匹配父commit更改源码；提交前核对复用helper在父commit存在，live产品/source若与父不同须披露replay限制，不静默附带产品差异或声称完整远端复现。临时index明确选路径，原raw/权重/wheel/overlay/JIT不提交；正常推研发分支并三SHA核对，任何拒绝不绕过。

共享src/model_control/service.py的其他未提交修改明确不触碰、不提交、不记作本轮成果。

## 验收

软件通过是实际原生子类和全预生成证据CPU可编码、sidecar完整、严格拒绝未知/cycle/nonfinite、主异常不被二次写失败掩盖、原文件SHA未变；它不是模型质量通过。实际运行、四组质量、速度/显存与正式验收继续按R486分别记录，质量优先、无raw清洗，正式NOT_PERFORMED。记录新修复、历史2次失败和限额变化；不伪称历史已有生成。

## 固定输入

完整path/bytes/SHA256见plan.json input_sha256，包含diagnostic-inputs中的15项、全部本轮原始异常及Astra实际类型检查、已安装TorchVersion/QuantizationStatus定义源码；实施前逐项复核。不将缺失未来证据标已存在。
