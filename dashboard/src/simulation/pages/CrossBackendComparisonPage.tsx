// 跨后端对比页面，只允许 paired key 一致的 MuJoCo/Isaac 结果比较。
import { Card, Descriptions, Tag } from "antd";

export function CrossBackendComparisonPage() {
  return (
    <Card title="Cross Backend Comparison">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Backends">
          MuJoCo / Isaac Sim
        </Descriptions.Item>
        <Descriptions.Item label="Pairing">
          scenario + seed + network + mode
        </Descriptions.Item>
        <Descriptions.Item label="Isaac">
          <Tag>BLOCKED_BY_ENV when unavailable</Tag>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
