# R478 Astra补充计划：加载API与量化模块匹配的内存适配

实际规划者：`gpt-6-astra`；不修改官方磁盘源或权重。

**原始失败：** 首次真实B加载读1066 tensors后finalize报list|set TypeError，actual_requests为空、requests_started=0；stderr另报vision_model.radio_model.model.patch_generator.embedder.weight_scale MISSING。checkpoint-header-readout证明embedder.weight为BF16[1280,768]、无scale，共248个FP8 weight；未发生OOM。原失败和runner副本已保留。

**根因及待验证假设：** 官方模型类_ignore unexpected元数据为list，新Transformers集合并集接口需要set；第二项是class-name Linear匹配加isinstance(nn.Linear)选中了checkpoint未量化的Linear子类。前者可保持pattern集合不变转换类型；后者需由真实FP8 weight/scale与meta模块集合逐项证明，不能以隐藏missing解决。

**限定范围：** 仅新增本轮artifact适配器或复制run_fp8_pair.py为新runner，运行进程内对官方model_class metadata及AutoConfig深拷贝应用窄适配；输出新model-run-b-r478目录、独立result，并让evaluator显式读取该新result。不得覆盖旧run/result或修改模型/config/safetensors、第三方磁盘源码、原计划、产品代码、量化数值或权重；不新增ignore pattern、不放行随机初始化。

**执行：** 先复核本计划输入SHA、R473权重manifest及完整权重SHA（12,672,885,688 bytes，c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a），验证header摘要。只读读取官方model_class，在本进程把_keys_to_ignore_on_load_unexpected的list转set，保存原类型/内容和转换后排序内容，断言pattern集合完全相等；原为其他类型按实际验证，不改missing-ignore，不新增regex。退出恢复类属性，磁盘源码不动。
从真实safetensors header中dtype为FP8的*.weight派生module全名；每个需存在对应weight_scale且shape满足官方channel量化语义，核对248个唯一名称，无多余FP8参数/无scale层。对AutoConfig作deepcopy，只将原group_0.targets由Linear改为248个re:^加re.escape(module_name)加$的锚定regex；按实际compressed-tensors regex语法验证。其余config、ignore、weights/activations、dtype、use_optimized_inference、dequantize设置保持不变，保存前后canonical JSON及精确diff（只许targets路径变化），将此公开标为artifact内存兼容适配。
使用不加载权重的meta skeleton、真实同版本replacement函数验证替换模块集合与checkpoint FP8 module集合完全相等，保存before/after module class和target mapping；特别检查BF16 embedder原class未换、不会创建weight_scale，FP8 scales形状可被原官方转换消费。meta阶段不得凭meta dtype声称读到了真实BF16值；BF16依据header，实际加载后另验证dtype。若集合不相等或不支持精确regex即停止，不用调整更多配置迁就。
通过meta门槛后清洁B环境、cache cwd、现有共享GPU锁执行一次新加载；记录output_loading_info和完整raw日志，missing_keys必须为0，mismatched/error必须为空，不允许ignore_mismatched_sizes或补零/随机初始化；unexpected keys原样记录并逐项对应既有官方pattern，不能新增隐藏项。实际248个FP8模块权重dtype/scale及embedder原class/BF16逐项验证。通过才执行同一冻结RGB/depth四次真实生成，输入/prompt/参数/processor证据按R473；第一次标first inference after corrected reload，不能称机器冷启动或未曾加载的冷启动。evaluator只按显式新result路径判分，保留旧失败为历史。

**验证：** 软件证据包括pattern集合不变、config diff仅targets、248个完整一一对应替换、零missing/mismatch及原文件SHA前后不变。真实运行包括加载、四次生成、双图processor证据、raw response、时延/显存和逐次JSON/定位质量；软件通过不代替真实运行。保留适配前失败、适配源码hash和完整选择依据，使结论明确是官方权重经本轮内存兼容适配的实测结果，不声称官方默认即开即用。

**预算及验收：** 继续原总3小时、不重置预算；加载<=600秒、每请求<=180秒、GPU准入free>=14000MiB且无其他compute进程、沿用共享锁、只GPU无offload。缺scale/集合不符/新的missing或随机初始化立即停；若需重写权重、新量化、第三方磁盘补丁或新根因，保留原始证据再交Astra。仅关闭本轮PID并释放锁/GPU。最终分别报告软件验证、真实模型运行、固定S01质量及正式验收NOT_PERFORMED；运行失败不回填成功。

**输入SHA：**同目录plan.json的input_sha256逐文件固定AGENTS、原R473计划、runner、官方config/modeling、TF实现及本轮全部诊断的path/bytes/SHA；实施前逐项复核。
