import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Tag, Tooltip } from "antd";

// 状态徽标只做视觉归类，权威状态仍来自 API 字符串本身，不能在这里改写业务语义。
type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toUpperCase();
  const isBlocked =
    normalized.includes("BLOCKED") || normalized.includes("NOT_STARTED");
  const isRejected =
    normalized.includes("REJECTED") || normalized.includes("FAILED");
  const isAccepted =
    normalized.includes("ACCEPTED") ||
    normalized.includes("VALIDATED") ||
    normalized === "READY";

  const color = isRejected
    ? "red"
    : isBlocked
      ? "gold"
      : isAccepted
        ? "green"
        : "default";
  const icon = isRejected ? (
    <CloseCircleOutlined />
  ) : isBlocked ? (
    <WarningOutlined />
  ) : isAccepted ? (
    <CheckCircleOutlined />
  ) : (
    <StopOutlined />
  );

  return (
    <Tooltip title={`状态: ${status}`}>
      <Tag aria-label={`status ${status}`} color={color} icon={icon}>
        {status}
      </Tag>
    </Tooltip>
  );
}
