# R423 可选basetemp归档步骤报告

实际gpt-6-astra补充计划在实施前11项输入pins全部匹配。本轮只修正行政采集假设，没有产品、测试、SQL、模型、网络或Git写入；未重跑任何pytest，R422原25预期RED及47GREEN证据保留。

首次归档错误为原脚本对red-001无条件assert source.is_dir()，tool chunk a209b6、exit1，首次复制前失败。该错误及空目标根保持记录，未删除或覆盖历史。源inventory72项为16个真实目录、56个当前不存在；不存在只记ABSENT_OBSERVED，不把缺失等同于完整历史上从未创建。

按最终计划只处理72个明确根：16棵实际目录create-only复制到R422/local-raw/<stage>，56项均copy_attempted=false、target_exists=false。共459个普通文件、17,266,800 bytes，副本逐项bytes/SHA256、目录结构/类型与symlink原文本相同；不跟随链接读取目标内容，链接边界、UID与文件类型核对通过。原16树结构/身份/内容before/after一致，56缺失状态未变，72个validation stage树摘要及11输入pins未变。

一次行政执行耗时0.332秒（cap300秒），exit0，无子进程或清理需求。没有自动重试、删除或伪造缺失raw；首次失败后仅执行这一实际Astra计划允许的采集/复制/核对。详细完整清单在local-preservation-manifest.json，为local-only，不属于Git交付。原绝对symlink仍可指向源，副本不声称自包含可移植包。

R422目录原有的完整stdout/stderr、resource/process详单和运行DB/raw原地保留，完整副本同样只在本地。新增Git文档仅R423的plan.md、plan.json、intake/observation.json和本报告；与R422合并一次fresh最终Astra审查，之后按精确清单正常提交/推送并核对三处SHA。归档核对不是正式研究或实体验收。
