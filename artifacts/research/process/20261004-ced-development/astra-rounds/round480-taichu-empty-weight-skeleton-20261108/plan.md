# R480 Astra补充计划：空参数结构预检

实际规划者：`gpt-6-astra`。

**失败与根因：** R479已越过SDPA传播门槛；meta scaffold的全局torch.device(meta)把timm torch.linspace小标量也置为meta，VisionTransformer .item()抛Tensor.item() cannot be called on meta tensors。原始v2日志/result已保存；这只证明结构预检构造方式不合适，尚无R478新实际加载或生成失败。

**范围：** 仅本轮artifact r478_adapter的空权重结构构造context与新runner所读门槛路径；采用已经安装的accelerate1.3.0，不新增包、不改环境，不补丁torch/timm/官方model，不改R478精确量化targets或R479既定SDPA。

**执行：** 复核本计划输入SHA。移除覆盖整个构造的torch.device(meta)，改用accelerate.init_empty_weights(include_buffers=False)构造同一model_class/config；参数注册后须是meta，普通小标量和buffers留CPU。保持配置深拷贝、SDPA传播、248个精确targets和ignore pattern集合不变。构造及量化替换后逐项记录named_parameters设备/numel/dtype，要求全部parameter.device.type==meta；记录named_buffers设备/bytes，总CPU buffer<=64MiB，禁止为检查加载权重或把meta参数materialize到CPU/CUDA。记录进程RSS基线/峰值，检查不存在额外大CPU权重副本；若构造产生无法解释的大分配或非meta参数则停止，不继续实载。
继续原R478完整meta模块集合验证：248个replacement与checkpoint FP8集合一一对应，BF16 embedder保留原class、未添scale；BF16存储依据仍来自header，不把meta视为实际加载证据。另存meta-scope-verification-v3.json及v3原始stdout/stderr，不覆盖v1/v2。新runner门槛显式读取v3，校验status、source/config/header/target摘要匹配，不因旧文件存在放行。

**验证及边界：** artifact语法检查与一次真实结构构造验证，无产品测试、无权重读入。要求全参数meta、CPU buffer<=64MiB、248精确集合及源文件hash通过；清理本轮skeleton后方继续同一R478一次实际load和同帧四请求，其余零missing/mismatch、量化dtype、时延、GPU锁与14GiB准入不变。v3失败保留新异常，若非已知构造问题另交Astra，不无限变换初始化路径。修复预检<=5分钟，原总3小时/600秒load/180秒请求预算不重置；软件、真实运行、质量和正式验收仍分别记录。

**输入SHA：**完整path/bytes/SHA256清单见plan.json，固定AGENTS、R478/R479计划、待改adapter及本轮原始诊断；实施前逐项复核。
