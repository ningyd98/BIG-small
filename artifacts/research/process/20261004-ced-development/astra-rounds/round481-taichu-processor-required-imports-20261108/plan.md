# R481 Astra补充计划：完整图像processor必需依赖

实际规划者：`gpt-6-astra`。

**失败与根因：** R478实际reload的248个FP8层、全GPU及zero missing/mismatch已通过；第一次请求在processor.from_messages懒导入vision_utils时因requests缺失失败，inference_calls_started=0。官方vision_utils无条件import requests；前置仅processor实例化未覆盖此入口。保留加载成功及后续失败的完整原始证据，不把该结果称为模型生成失败或模型双图通过。

**范围：** 仅runtime-b追加requests2.34.2和其实际缺少的非extra传递依赖、artifact完整processor预检与新的model-run-b-r481输出。原64包所有版本保持不变；不改官方代码/权重/量化、248精确适配、attention、提示词/生成参数，不安装视频extra或升级整库。

**执行：** 复核输入SHA及干净B现有freeze/64版本基线。requests官方metadata已固定：requests-2.34.2-py3-none-any.whl，73075 bytes，SHA256 2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0。检查现有charset_normalizer>=2,<4、idna>=2.5,<4、urllib3>=1.26,<3、certifi>=2023.5.7；满足则复用，不满足的已安装包不能升级，需停报约束冲突。只有缺少者可从官方PyPI JSON选择满足条件的固定版本，先保存metadata和wheel name/version/size/SHA清单再下载。沿用enp7s0/AliDNS/TLS/精确TUNA及PyPI allowlist、无代理、上游SHA校验、wheel-only和离线--no-index安装；最多新增上述5个包，总新增wheel<=2MiB。
干净B env/cache cwd重新pip check、freeze，验证原64版本逐项不变且新增闭包完整。静态复核processing/vision_utils图像入口必需imports；已有numpy/torch/PIL/Transformers需实际导入，decord等视频路径未使用可选，不为本轮安装。先真正执行processor.from_messages的完整固定双图路径，保存steps/processor-b-r481及raw、两图hash、模板/token/张量dtype/shape/原字节hash；只使用本地固定图，不让requests联网取图，不加载权重或warmup。
完整processor门槛通过后，复制/配置新runner及唯一model-run-b-r481输出，沿用R478/R479内存适配和详细v3门槛进行一次新load与同帧四请求；记录first inference after corrected reload，不声称机器冷启动。旧R478模型load成功但processor失败的run-result保持不变，evaluator显式使用新result。

**验收与预算：** 软件验收：上游SHA、干净pip check、64版本不变、完整processor两图真实预检通过；随后真实load仍须zero missing/mismatch、248FP8/原BF16层正确、GPU锁/14GiB准入、无offload。逐次真实生成/JSON/定位另行判分，正式验收NOT_PERFORMED。本轮仅为新增微型依赖和验证追加最多5分钟依赖工时，原40分钟历史如实保留并标注此独立扩展；总3小时、load600秒和每请求180秒不扩大、不重置。超时/网络或新增闭包失败立即停止；其他新必需依赖、原64变更或新根因另交Astra，不先修后补计划。

**输入SHA：**plan.json完整固定AGENTS、R473/R478计划、B运行选择、官方processing/vision_utils及本轮全部原始失败/成功加载/requests metadata的path/bytes/SHA256；实施前逐项复核。
