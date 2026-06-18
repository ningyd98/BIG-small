// 模式对比页面，比较 PCSC、ETEAC 和 AUTO 的成功率与通信指标。
import { Card, Descriptions } from "antd";

export function ModeComparisonPage() {
  return (
    <Card title="Mode Comparison">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Modes">PCSC / ETEAC / AUTO</Descriptions.Item>
        <Descriptions.Item label="Metrics">
          success rate, completion time, cloud calls, communication, retries,
          replans, mode switches, safety interventions, recovery time
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
