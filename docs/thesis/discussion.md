# 讨论

PCSC 与 ETEAC 的适用边界主要来自云端调用频率、通信等待和本地恢复能力。AUTO 的有效性需要在网络退化和故障注入条件下看综合指标。SafetyShield 的代价表现为安全拒绝与停机事件，但 unsafe command 必须始终为 0。

MuJoCo 与 Isaac 的差异只能说明 sim-to-sim gap。没有真实硬件实验时，论文不能声明完成 sim-to-real 实证。
