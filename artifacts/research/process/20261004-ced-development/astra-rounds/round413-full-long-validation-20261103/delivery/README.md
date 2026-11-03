# R413 精选证据交付边界

被测代码为 ab18abd0f82a024b62f4423c946c6585f8d18c65；报告提交只新增证据，不表示对新报告提交重新执行整套长测。

core-manifest.json 是whole-evidence review前的精确路径/字节/SHA选择。最终selected-manifest.json还会纳入fresh review与本交付说明等明确文件；实际Git stage列表使用独立NUL路径文件。推送回执在本目录本地保存，因包含本次commit SHA而不属于该commit。

R416补充计划仅处理.gitignore的reports/准入，见../../round416-selected-report-ignore-admission-20261103/step-report.md。它允许一次字面路径NUL清单的git add -f；这只是登记明确报告文件，不授权force push，也不修改.gitignore。

审核后元数据只允许追加本目录core-manifest.json、core-paths.txt、selected-paths.nul、selected-manifest.json，../review/whole-evidence-review.md与.json，以及R416/admission/final-ignore-audit.json。README本身已在核心清单。核心字节审核后冻结；新增文件也逐路径审计忽略规则。selected-paths.nul先写定（包括自身及最终manifest路径），selected-manifest.json记录其SHA及其它每个文件SHA，但不包含自身SHA；最终manifest另在本地Git门禁回执单独hash，以避免自指。最终清单未获通过前不stage。

完整批量raw、运行数据库/WAL/SHM、/tmp、缓存、重复fixtures、图像/trace、凭据、模型权重和SDK保持本地，不在精选包内。Phase12完整raw/manifest只记录SHA与大小；精选审计和个别原始回执不能冒充完整远端复现包。原static-docs敏感内容扫描详情保留本地；提交中使用脱敏分类。

报告保留35项Python失败、6项backend参数化skip、1项未完成及2项真实数据未运行。Mypy入口未形成有效源码类型检查，不能视为类型检查通过。正式研究/实体硬件验收未完成。源/清理/唯一STARTED核验与原始失败分开记录。
