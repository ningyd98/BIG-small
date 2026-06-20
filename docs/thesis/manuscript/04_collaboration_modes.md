# 第四章 双模式云边协同机制

## 4.1 PCSC

PCSC 是周期云端监督模式。边缘端按序列号上传 Telemetry，云端返回 KEEP、UPDATE、PAUSE、REQUEST_OBSERVATION 或 ABORT。TTL、version、sequence 和 ACK 用于拒绝过期命令和乱序更新。PCSC 适合高风险、高动态或需要频繁云端监督的场景，但通信开销较高。

## 4.2 ETEAC

ETEAC 是初始规划加边缘事件自治模式。云端生成初始 TaskContract 后，边缘端在事件检测、本地恢复和 FailureSummary 机制支持下执行任务。ETEAC 在网络退化或云端中断时更依赖边缘自治，适合风险可控、场景变化可由本地机制处理的任务。

## 4.3 AUTO

AUTO 不是第三类执行器，而是 PCSC 与 ETEAC 的选择器。它根据风险分数、网络质量、场景动态性、技能缓存命中和历史恢复情况做模式选择，并通过防抖和切换约束降低频繁切换风险。

