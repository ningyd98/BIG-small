# R479 Astra补充计划：传播既定SDPA配置

实际规划者：`gpt-6-astra`。

**失败与根因：** R478 meta _from_config只在顶层指定SDPA，嵌套llm_config仍为flash_attention_2，构造Qwen3_5时抛缺FlashAttention2的ImportError；原始meta stdout/stderr/result已保存。实际R473原调用已用SDPA读完权重，故这是meta/实际配置传播不一致，不是新增安装FlashAttention的理由。

**范围：** 仅本轮artifact r478_adapter及其新runner门槛，使用配置深拷贝传播已有SDPA选择；不改官方config/configuration/模型/权重/第三方磁盘源码，不改R478的248精确targets或量化语义，不安装编译flash-attn。

**执行：** 实施前复核固定输入SHA。用官方AutoConfig.from_pretrained(local_files_only=True,trust_remote_code=True,attn_implementation="sdpa")的已有构造传播逻辑，或对隔离配置深拷贝显式设置top._attn_implementation="sdpa"、llm_config._attn_implementation="sdpa"、vision_config.use_flash_attn=False；检查实际嵌套对象而非仅字典序列化。保留R478原targets派生与其他配置；记录传播前后attention值及diff，量化配置除R478 targets外完全一致。对meta调用_from_config仍显式传sdpa。
保存新meta-scope-verification-v2.json与v2原始日志，保留旧失败；新runner门槛明确读取v2并验证status/248精确集合/输入hash，不以旧文件存在代替通过。真实from_pretrained必须接收同样经验证的派生配置且继续显式attn_implementation="sdpa"，防止嵌套默认覆盖；保留R473其余加载参数和R478零missing等所有门槛。实际模型构造后记录各子config的attention值，不接受隐式FA2回退。

**验证及边界：** 先只做完整meta替换集合验证：248个FP8模块完全对应，非FP8 embedder原class保留，量化与源文件SHA未变。通过后继续R478一次实际重新load+同帧四次生成，不另增加warmup或改冷启动标记。若仍有非传播根因则保存异常再交Astra，不安装新attention backend。沿用原3小时总预算、600秒load、180秒/请求、GPU准入/共享锁/无offload；R479 meta修复<=5分钟且不重置预算。软件、真实运行、质量、正式验收继续分列。

**输入SHA：**同目录plan.json完整固定AGENTS、R478计划、adapter、官方configuration及原始诊断的path/bytes/SHA256，执行前逐项复核。
