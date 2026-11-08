# R499 — 精确 token 序列子集资格

实际规划模型：gpt-6-astra；仅规划。完整输入SHA及精确禁用ID见plan.json。

批准一次新的限定资格：明确以闭合集合D全程硬禁替代“分类等价”前提，保留R498单187否决。实际D为 **28项=187+27个原added_tokens**；R498文字的27项计数在此纠正，旧原件不改。新证据确认D在探测字符串状态全禁，且 `<think>` 用普通ASCII七token仍可构成相同raw、完整schema接受并允许原三EOS。这证明替代分词实例，不证明所有tokenization或完整文本语言等价。

新byte_decoder_r499.py必须重新核对全词表：分类差集精确D，唯一byte例外187:ff→空，D其余27均与原added内容bytes吻合，其余零差异。每步复制native mask后仅把D置0，缓存/消费/最终membership都检查有效mask，EOS/错误/空mask门槛不变；不得开放token、remap、吞异常或更改库、tokenizer/schema。原1030多模态prefix不送parser。provenance如实列28分类差异和1byte例外；禁187排除HF lossydecode部分路径，非等价声明。

原21项（6合法/11非法/4值边界）原字节与预期必须全部通过；另对D的27个added字符串逐个以普通ASCII字符token做完整schema存在性见证，raw一致且终态三EOS可达。实际生成不强制这种分词，只维持greedy合法mask选择。原prefix/EOS/cache/视觉/72包/codec及R494真实硬件门槛全部保持。唯一新CPU报告/runner导入与目的地，旧失败代码不改；任何未知差异或契约失败即最终负门槛，不继续扩大集合或修复。

CPU含附加见证≤120秒且 **15:43:20 UTC** 截止，整体 **16:19:20**、A16:00/B16:04:20窗口不变；最大1load/24gen不增加。CPU资格PASS才继续原八次对照，B仍需专项来源计划。生成结果必须披露固定属性序和禁28ID的搜索空间子集，不能声称分类等价或只改变schema因素；格式/定位/正式验收分列，保留所有旧负结果并沿用原R491交付。
