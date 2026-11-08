# R487 Astra限定计划：保留结构的证据集合序列化

实际规划者：`gpt-6-astra`；仅规划，未实施。

**原始失败及根因：** R486首次loader已返回（1.890742591秒），artifact experiment.save普通json.dump遇loading中的set报TypeError，留下20-byte loading-info.partial。尚未完成missing/inventory门槛，未保存model-config，0请求/0生成；不能将loader返回说成完整兼容验收通过。另收集helper误以为后续文件已存在而FileNotFoundError，原证据已保留，按实际阶段记录不存在，不补造文件。

**范围：** 仅新增artifact evidence序列化适配及新runner/output引用；优先复制experiment.py为experiment_r487.py，仅改变save证据编码，复制run_profiles为run_profiles_r487.py，仅改helper导入和唯一raw/result路径。原runner/helper/protocol、20-byte partial、raw/log和原run-base.json不动；不改模型内存loading结构、量化/参数/attention、视觉输入、产品或第三方代码。独立wheel下载/静态核查可继续。

**执行：** 复核输入SHA；证据encoder只为set/frozenset添加确定性JSON数组表示：递归规范化各元素，使用规范JSON字符串作为排序键保证同集合多次输出一致，空集合编码[]；记录每个转换的JSON Pointer路径、原类型set/frozenset、元素数及编码规则到独立serialization sidecar。正常JSON dict/list/scalars保持内容/类型语义，已有tuple等json原生接受的表示不通过str降级；未知类型、循环引用、非有限值仍显式失败，禁止default=str/宽泛repr。不mutate原值，内存missing/mismatch/unexpected检查继续使用原loading对象。先完成全量规范化和json.dumps(allow_nan=False)再以exclusive-create写新证据，防止编码失败新造半截JSON；原半截不删不补。
CPU前置覆盖empty/nonempty set、frozenset、嵌套普通dict/list、异构可JSON编码元素、正常纯JSON及未知自定义对象拒绝；验证排序稳定、sidecar路径准确、输入对象未变、纯JSON往返内容一致。只读冻结当前TF loader返回结构相关源码；若可直接构造LoadingInfo/实际返回字段结构则不载权重验证相同字段编码，明确这是结构单测而非实际模型loading证据。无需添加产品测试。原收集helper仅按文件实际存在性收集，缺失文件记NOT_CREATED_AT_FAILURE_STAGE，不创造空文件。
前置通过后新run_profiles_r487仅使用新raw leaf/run-base-r487.json（若B随后用同helper同样新独立B路径），保持R486冻结ON,OFF,OFF,ON,ON,OFF,OFF,ON、图像/token一致门槛、全部HF参数不变。新loader成功返回后保存原结构编码证据，再执行原zero missing/mismatch、248FP8/GPU/BF16层检查，只有全部通过方可生成。evaluator显式读取新run结果，旧失败不得被后续成功覆盖。

**验证与验收：** 保存CPU验证源码/输出/rc、新旧artifact差异、序列化sidecar及所有输入SHA前后检查。编码修复通过只表示证据能够忠实保存；后续模型/思考开关/质量各门槛依R486，不能绕过未到达的inventory。未知对象若再失败保存真实类型/路径/traceback并停，不自动把新类型str化。missing历史文件准确NOT_CREATED，保留收集错误。

**前置及预算：** CPU修复验证<=5分钟，R486总90分钟不重置。明确允许一次替代A加载：历史已有1次loader返回，余下A一次+B至多一次，总load上限从2调整为3；总真实生成仍<=16（A8+B最多8），无额外warmup，load600秒/请求180秒不变。新load前复核GPU>=14000MiB/共享锁/无其他compute；一次历史14600MiB不替代当前准入。OOM/新根因/未知编码类型立即停止相关修复并新Astra，独立证据工作可继续。只关闭本轮PID；无环境安装/产品修改。

**固定输入SHA：**plan.json完整列AGENTS、R486计划/helper/runner/protocol/run结果和R487全部原始副本/partial/异常的path/bytes/SHA256；实施前逐项复核。
