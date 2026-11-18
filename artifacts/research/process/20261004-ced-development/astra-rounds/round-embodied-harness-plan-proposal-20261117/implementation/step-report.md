# Harness计划书与开题报告修订步骤报告

日期：2026-11-17（Asia/Shanghai）。原始需求：参考SenseNova-RoboRSI Harness，将BIGsmall最终封装为面向具身智能的harness，更新项目计划书与开题报告。实际gpt-6-astra先生成本轮计划；本报告只记录文档交付。

## 实施与核查

1. **适用性：** 实施前9直接输入和9快照SHA一致，HEAD为025c538935199ea7d3aa8cf15b6e93ac9826cf3a，index空。既存simulation/config.py、两个嵌套工作区和无关未跟踪材料排除。
2. **计划书：** docs/plan.md增加现行Harness定位、三层架构与六类拟定契约、参考机制映射、H0—H4/原六工作包对应、条件排期、发行清单、分层复现验收和后置离线改进。原旧全文40,546字节作为历史后缀逐字保留。
3. **开题报告：** 更新依托项目、选题意义、RoboRSI相关工作、当前云角色、三研究问题与共同工程基础、工程交付、七章目录及2027年4月条件排期；论文题目、专业、申请日期、专利事实边界及量化表保持。
4. **入口：** docs/README.md提供两份现行主文档、11月8日六包路线图、10月4日研究设计；10月初开题资料标为历史，未替换旧Word/DOCX原件。
5. **来源：** 官方仓库固定9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555；读取README、Agent配置及评测文档。固定SHA README与首次main正文相同。公开摘记见sources/reference-notes.md，完整抓取本地保存。

## 验证及原始失败

采用verification-before-completion流程，使用python3标准库检查并人工核对语义。最终一次完整验证退出0，35项全部通过，详见validation.json及Git路径修复轮validation-rerun.txt（chunk 2a4e81）。包括计划/清单hash、9冻结原件、非目标输入不变、历史后缀、引用/本地链接、代码围栏/表格、现行模型/原题目、冻结边界、git diff --check及修改范围。

人工核对三研究问题对应G3、G2/G2a、G4，共同G0/G1及B0资格保持；云gpt-6.1-sol、边缘规则成本/模型后置、OpenCV/RGB-D/标记/相机/控制器保持。成功率、安全、调用、字节、延迟、恢复目标及样本/分组隔离/惩罚/冻结规则与11月8日路线图、10月4日设计一致。Harness全部写为拟交付，已有模块、历史证据和未验收能力分开，版本改进不借用正式测试或真值。

首次脚本ROOT路径偏一层，FileNotFoundError退出1，原始输出见validation-attempt-1.txt；实际Astra制定[根目录修复计划](../../round-embodied-harness-doccheck-root-20261117/plan.md)，仅改ROOT一行。随后35检查中34通过，范围检查因Git中文路径C转义误判；实际Astra制定[Git路径修复计划](../../round-embodied-harness-doccheck-gitpaths-20261117/plan.md)，仅改NUL路径读取。原FAIL JSON和stdout/stderr保留，未修改白名单或正文使检查通过。两修复轮各有输入SHA和修复报告。最初Astra规划时python别名缺失原记录也保留，后续用已存在python3。

## 分层结果与交付

- 文档验证：PASS；三份正文已同步且历史原件保持。
- 产品单元/集成测试：NOT_RUN，本轮没有产品代码改动。
- 实际模型API、物理仿真、真实机械臂、训练：NOT_EXECUTED。
- 正式研究：NO_NEW_ACCEPTANCE，不宣称Harness已实现、发布或研究通过。
- Git：交付前只读远端与输入HEAD一致；按delivery-manifest.json精确路径提交推送，最终三SHA核对另保存本地回执并在用户结果中报告，不在提交前预称成功。

发行载荷仅含三份文档及必要小型过程文件。原件快照、完整外部抓取、完整raw、DB、凭据、权重和SDK不在本次清单内。validation脚本的快照检查需要完整本地输入，远端文档与清单不构成完整复现包。后续实际运行按最新适用Astra计划、动作资格、数据隔离、预算、资源锁和原安全条件推进。
