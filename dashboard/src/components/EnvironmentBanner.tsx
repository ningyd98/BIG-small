import { SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, Space, Tag, Tooltip, Typography } from "antd";

import { StatusBadge } from "./StatusBadge";

type EnvironmentBannerProps = {
  projectStatus: string;
  realRobotValidation: string;
  highestAcceptanceLevel: string;
};

export function EnvironmentBanner({
  projectStatus,
  realRobotValidation,
  highestAcceptanceLevel,
}: EnvironmentBannerProps) {
  return (
    <Alert
      banner
      showIcon
      icon={<SafetyCertificateOutlined aria-hidden="true" />}
      type="info"
      title={
        <Space wrap>
          <Typography.Text strong>
            MoveIt dry-run，仅规划，不执行硬件动作
          </Typography.Text>
          <StatusBadge status={projectStatus} />
          <Tooltip title="真实机械臂验证尚未开始，控制台不会提供硬件运动入口。">
            <Tag
              aria-label={`real robot validation ${realRobotValidation.replaceAll("_", " ").toLowerCase()}`}
            >
              真实机械臂验证：{realRobotValidation}
            </Tag>
          </Tooltip>
          <Tag aria-label={`highest hardware level ${highestAcceptanceLevel}`}>
            最高硬件级别：{highestAcceptanceLevel}
          </Tag>
        </Space>
      }
    />
  );
}
