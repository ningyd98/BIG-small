import { Card, Collapse, Space, Tag, Typography } from "antd";

const levels = [
  "LEVEL_0",
  "LEVEL_1",
  "LEVEL_2",
  "LEVEL_3",
  "LEVEL_4",
  "LEVEL_5",
  "LEVEL_6",
];

export function SafetyAcceptancePage() {
  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="安全验收">
        <Typography.Paragraph>
          当前最高真实硬件验收级别为 <strong>NONE</strong>
          。所有真实动作保持锁定；控制台只展示准备状态和证据。
        </Typography.Paragraph>
        <Tag color="gold">未配置真实控制器</Tag>
        <Tag color="gold">无真实遥测</Tag>
        <Tag color="red">禁止运动动作</Tag>
      </Card>
      <Collapse
        items={levels.map((level) => ({
          key: level,
          label: `${level} 已锁定`,
          children:
            "Phase 10.2B 只允许查看定义、阻塞项和证据，不允许标记通过或执行动作。",
        }))}
      />
    </Space>
  );
}
