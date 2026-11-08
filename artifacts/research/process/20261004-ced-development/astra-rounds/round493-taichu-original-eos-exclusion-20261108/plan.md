# R493 Astra限定计划：原EOS从regular-token集合排除

实际规划者：`gpt-6-astra`；仅规划，未实施。

**失败与假设：** 4个真实tokenizer合法fixture在target_label开引号后均出现allowed EOS248040且parser.can_end=false，原guard正确拒绝，尚无model load/generate。build_data仅过滤tokenizer.all_special_ids，模型原EOS之一可能不在该集合，被收进regular free-text快捷路径。原generation_config的EOS=[248044,248040,248046]，248040同时bos/pad；不能删改原模型EOS来掩盖问题。TF convenience adapter导入不兼容后使用backend-agnostic路线已由R491授权，不是本轮新增框架变更。

**范围：** 仅新artifact backend_r493.py的TokenizerData regular-token排除集合，及引用它的新CPU gate/必要runner导入和唯一结果名；原backend/test/日志、protocol、依赖71+2、prompt/schema/视觉输入/1030token、HF配置与模型均不改。保留原4失败，使用cpu-backend-r493.*新输出。

**执行：** 复核输入SHA；先从真实tokenizer记录all_special_ids和原3 EOS，确认E减S及248040分类事实。build_data使用excluded=set(tokenizer.all_special_ids)|set(original_eos_ids)，仅在regular-token构建时跳过excluded；保留TokenEnforcerTokenizerData.eos_token_id完整原3个及原顺序，HF generation_config/EOS/pad/bos不改。记录旧/新regular ID集合差集，要求精确等于E减S且不误删其他普通词/Unicode token；保存regular数量/hash、S/E/excluded及新增过滤ID的token表示。
原boundary-aware tokenizer decode、Unicode算法、schema投影、prefix-state/1030前缀处理、allowlist和premature-EOS guard全部保持。不能在callback中事后静默丢EOS代替修TokenizerData，不能关闭guard/返回无约束/改成只一种EOS。若E或数据边界不是根因，停止保存证据，不新增其他修复。

**验证：** 新CPU测试基于真实tokenizer完整重放原4合法fixture及R491原结构/Unicode/prefix/cache隔离验证；逐每个非终态确认3 EOS均不在allowed，终态can_end=true时全部3 EOS可达，allowed非空。逐token合法JSON必须仍可生成，原负例/core-schema门槛保持；记录新过滤集合精确、其他regular tuples/decoder算法内容不变、重复请求/相同prefix无泄漏、1030token输入和视觉hash未变。原依赖和HF配置SHA不变。新CPU门槛通过后才按原R4918顺序运行，runner草稿如需换backend导入须记录最小diff，不扩生成范围。

**预算及边界：** 依赖/CPU截止15:14:20UTC、整体16:19:20UTC不重置；实施前检查剩余时间，过阶段预算则STOP_BUDGET而非忽略。只CPU修复/验证，无GPU模型warmup；正常网络/依赖不需重装。原允许的API候选和schema等价变换继续，其他预期不支持记负结果，不无限修复。新根因/过滤集合不吻合/未知token问题保留真实错误交Astra，不静默schema fallback。通过仅代表EOS过滤适配与原CPU契约，不代表真实JSON或定位质量已通过。

**输入SHA：**plan.json固定原6项、AGENTS、failure.json及原generation_config的path/bytes/SHA256，执行前逐项复核。
