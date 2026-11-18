# 官方参考核查摘记

核查日：2026-11-17（Asia/Shanghai）。官方仓库：OpenSenseNova/SenseNova-RoboRSI。固定提交：`9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555`。本地 `official-sources.json` 保存读取返回正文；后续固定 SHA 的 README 读取与首次 main 正文完全一致。

| 官方来源 | 已核查内容 | 对本轮规划的启发 |
| --- | --- | --- |
| [README](https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555/README.md) | Harness连接模型、技能和工具，记录轨迹；RSI复评候选改动；27B模型训练是另一个层面的扩展 | 本项目以既有运行底座封装Harness，受控离线改进作为后置能力 |
| [文档目录](https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555/docs/README.md) | 任务定义及原生评分由对应环境负责 | 保留BIGsmall独立物理评分与在线证据的职责区分 |
| [Agent配置](https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555/docs/agents.zh-CN.md) | 模型、提示、上下文、预算可配置；声明源码/资源后可导出安装包，模型服务和模拟器依赖另行准备 | 最终成果包含显式依赖、版本化配置、可安装组件和示例 |
| [评测](https://github.com/OpenSenseNova/SenseNova-RoboRSI/blob/9e7e7ad17b8957a5b8a530b8f4a0bbc11bb00555/docs/evaluation.zh-CN.md) | 执行、状态、比较、恢复有统一入口；版本名称不等于已验证运行依赖；保留旧批次引用 | 对齐实际运行身份后才能比较，恢复保留原记录和预算；软件替身与原生实验分层 |

以上均为来源摘要。下游的BIGsmall模块组织、H阶段里程碑和发布验收是本轮项目规划，不是商汤官方能力声明或实验结论。未采纳外部排行榜分数作为本项目指标，未执行RoboRSI安装或评测命令。
