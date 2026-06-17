import { LockOutlined } from "@ant-design/icons";
import { Card, Empty, Space, Typography } from "antd";

type SafetyGateCardProps = {
  hardwareMotionAuthorized: boolean;
  reasonCodes: string[];
};

export function SafetyGateCard({
  hardwareMotionAuthorized,
  reasonCodes,
}: SafetyGateCardProps) {
  return (
    <Card
      title={
        <Space>
          <LockOutlined />
          硬件执行门
        </Space>
      }
      size="small"
    >
      <Typography.Text strong>
        是否允许硬件运动：{String(hardwareMotionAuthorized)}
      </Typography.Text>
      {reasonCodes.length === 0 ? (
        <Empty
          description="无授权硬件运动；当前页面仅展示规划和验收状态。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <ul className="plain-list compact-list">
          {reasonCodes.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
