# EGL 诊断部分终态的类型与身份读回

实测版本 902c270251a9b5c4076a7cf8022621bf4d4d5ebb 的正常 cutoff 读回中，line 202 从 load_json 的 Any 直接返回、嵌套 .get 对非对象也无检查。实际定向 mypy 32 项/3文件；同相对路径基点 290ba377 为31项/2文件，唯一新项 no-any-return。旧实测已提交保全。

仅修改 native_checkpoint_diagnostic.py 的 RuntimeError 后读取已发布 collection-result.json 的出口，和 tests/test_native_checkpoint_diagnostic.py 的针对此出口回归。用运行时类型收窄而非 ignore、Any cast。首先验证顶层/嵌套 JSON 对象，顶层 COLLECTION_PARTIAL、唯一诊断 assignment、scope 与嵌套 scope；嵌套 CUTOFF、registration_sha256 等于本次登记的 digest(registration)，两层严格整数零资格，已完成的 final_lifecycle_receipt、执行与教师准入均 false、native_qualification UNKNOWN，并核原第一动作截止的 primary 原因。以原发布者真实语义判别，不把参考运行的绝对时钟/步数、随机job id、原件字节 SHA 或其他次要事件写死到产品。保留真实失败/清理信息；其它 RuntimeError、缺失/非字典/解析失败与伪造 cutoff 一律不能成为正常结果，保留初始异常可追踪。保持 finally 来源核查、部分回执 CLI exit1 及既有独立完整 reader。

先核实已提交实测源、冻结源码及近邻 helper 消费方。原结果 SHA 96b08db685360f31d2d059f642523a38b598ce810b6ced9a7efec732c6ed793c；registration 文件字节 SHA 与 canonical digest 是不同域，原内层实际为 ceb7a99e192e577c4d02284e57f5a8887923f17341f3932fd1e49bc7a32fef0e。原实测 SQLite job 的真实终态为 BLOCKED_BY_ENV。只用本地原冻结回执只读测试，不启动 worker/注册新 claim/EGL/模型。

## 验收

通过新实现的同一只读解析分支输入已冻结原件与原登记证明，对象完整相等，并保留公开 status/CLI 失败语义；可用小夹具验证外层 RuntimeError 路由。新反控包括标量/list、空或坏结构、wrong assignment/digest/scope、其他终态、无 primary cutoff、布尔 false 冒充资格0或资格大于零，及相关 RuntimeError 别因。不得只靠孤立的 CUTOFF 字符串。

按原相对源码路径、四模块、--follow-imports=silent --no-incremental 作源码 mypy 对照。未修的31条按目标名和内容与原基线逐项归并并明确记录，修后新增目标为零，不宣称旧库 mypy 全绿。运行旧诊断专项及 scoped Ruff，原独立 reader 双读、正式拒绝证据、源码/数据库/claim/回执 SHA 保留。新增软件验证不重复物理、云、模型或正式试次。

逐件 SHA256 见 [plan.json](plan.json)。
