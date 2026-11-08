# R482 Astra计划：离线评分snapshot元数据适配

实际规划者：`gpt-6-astra`；仅规划，尚未实施。

**问题、原始失败与根因：** 四次实际生成已完成，R481记录248个FP8保留、各512输出tokens。离线evaluator在构造ModelConfigSnapshot时因HF字段do_sample/max_new_tokens/num_beams不在产品允许列表而ValueError，尚未评分。model_resolver.py明确仅接受非空temperature/num_ctx/num_predict/top_k/top_p/seed/think；_ground_response只对原始response文本做VisualDecision严格解析及坐标grounding，不调用模型。根因是artifact把HF实际运行元数据误塞进产品接口快照，非产品validator缺陷。

**范围：** 仅新增artifact evaluate_pair_v2.py及唯一v2评分/参数说明输出，保留原evaluate_pair.py、失败stderr、所有四份raw/token/时间记录。产品validator/parser、snapshot类、真实模型/生成配置、提示词不改；不联网、不载权重、不重生成、不调用planner.plan/_request_visual/_post或任何硬件。

**执行：** 复核固定输入SHA及四份raw-response与run-result中SHA一致。新脚本显式要求R481成功run-result路径和唯一新输出路径，拒绝覆盖旧文件。为离线坐标/身份描述保留原snapshot尺寸、normalized_1000、grasp_profile、weight digest等，仅generation_parameters使用合法最小投影{"num_predict":512}。这个字段仅对应已记录的HF输出token上限，绝不声称全部HF参数映射；另显式记录snapshot_scope="OFFLINE_SCORING_ONLY"、snapshot_generation_parameters_are_not_effective_hf_config=true、provider/loopback endpoint仅为本地解析适配标识、未起服务/未发送请求。不得伪造temperature=0、think=false、HF provider兼容接口或推导不存在的参数。
独立保存完整hf_execution_parameters证据：实际运行generation-config.json的完整内容和SHA、真实runner显式override全部值do_sample=false/max_new_tokens=512/num_beams=1/use_cache=true/return_dict_in_generate=false/output_scores=false，以及runner/run-result/source SHA；说明调用override覆盖generation_config，其他值原样继承，不把离线snapshot当运行快照。记录skip_special_tokens=True和保留special token文本来源；两类原始输出均不修改。
对四份完整raw-response.txt逐一运行原VisualDecision.model_validate_json(strict=True)、原_ground_response及既有坐标/_pixel_hit检查。不得剥离思考、截取JSON、补括号、补字段、缩短回答或替换parser使其通过。解析失败输出MODEL_OUTPUT_INVALID_JSON、strict_json/grounded/quality_pass=false，target/destination hit=false并明确未得到合法坐标，不能解释成实际定位到错误像素；保留schema_error/parse_error和raw SHA。所有相同响应仍按四次预注册重复计数，不当四独立场景。

**验证：** 执行前确保项目输入、run/token/raw文件均只读；只做新artifact语法校验和一次离线评分。验证合法snapshot通过原校验、4条结果对应4个真实请求、raw SHA及512 token计数不变、HF元数据独立完整保留、调用路径无网络/生成。严格失败计数由真实parser输出计算，不能硬编码预期0/4；质量失败属于已计划负结果，不另修回答。_ground_response解析失败时raw_text为空不代表真实模型没输出，报告必须使用保留raw及其hash解释。评分后复核原evaluator、产品源、generation_config与4份raw SHA未变。

**前置与验收：** 使用原项目可用环境做纯离线评分，预算<=5分钟且原总预算不重置；所有capture/instance和raw必须存在并匹配hash。最终软件验收是评分工具成功完整产出4条真实结果；兼容性/生成完成沿用R481，质量按严格JSON与定位结果独立判负或判定，正式验收NOT_PERFORMED。含思考且达到512上限的截断仅据raw/token事实报告，不通过此轮解决。新的文件缺失/漂移或不同根因保留原失败并暂停，不更改真实实验字节。

**固定输入SHA：**plan.json的input_sha256逐文件记录AGENTS、R473计划、产品resolver/planner/probe、evaluator、R481真实runner/run/config、4份raw及tokens、capture/instance与本轮全部诊断的path/bytes/SHA256；实施前逐项复核。
