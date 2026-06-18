import {
  DashboardOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Space, Typography } from "antd";
import { Link, useLocation } from "react-router-dom";

import { useDashboardSummary } from "../api/queries";
import { useDashboardSocket } from "../api/useWebSocket";
import { EnvironmentBanner } from "../components/EnvironmentBanner";
import { DashboardRoutes } from "./router";

const navItems = [
  {
    key: "/",
    icon: <DashboardOutlined />,
    label: <Link to="/">概览</Link>,
  },
  {
    key: "/simulation",
    icon: <ExperimentOutlined />,
    label: <Link to="/simulation">仿真工作台</Link>,
  },
  {
    key: "/simulation/scenarios",
    label: <Link to="/simulation/scenarios">场景库</Link>,
  },
  {
    key: "/simulation/batch",
    label: <Link to="/simulation/batch">Batch/Sweep</Link>,
  },
  {
    key: "/simulation/live",
    label: <Link to="/simulation/live">Live Run</Link>,
  },
  {
    key: "/simulation/analysis",
    label: <Link to="/simulation/analysis">结果分析</Link>,
  },
  {
    key: "/task-execution",
    label: <Link to="/task-execution">任务执行</Link>,
  },
  {
    key: "/safety-acceptance",
    icon: <SafetyOutlined />,
    label: <Link to="/safety-acceptance">安全验收</Link>,
  },
  {
    key: "/evidence",
    icon: <FileSearchOutlined />,
    label: <Link to="/evidence">证据浏览</Link>,
  },
  { key: "/comparison", label: <Link to="/comparison">指标对比</Link> },
  { key: "/audit", label: <Link to="/audit">审计事件</Link> },
];

export function App() {
  const location = useLocation();
  const summary = useDashboardSummary();
  const socket = useDashboardSocket();
  const projectStatus = summary.data?.current_project_status ?? "UNKNOWN";
  const realRobotValidation = summary.data?.real_robot_validation ?? "UNKNOWN";
  const highestAcceptanceLevel =
    summary.data?.highest_acceptance_level ?? "NONE";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider width={248} theme="light">
        <Space orientation="vertical" size="small" style={{ padding: 16 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            BIG-small 控制台
          </Typography.Title>
          <Typography.Text type="secondary">
            实验与安全验收控制台
          </Typography.Text>
        </Space>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={navItems}
        />
      </Layout.Sider>
      <Layout>
        <EnvironmentBanner
          projectStatus={projectStatus}
          realRobotValidation={realRobotValidation}
          highestAcceptanceLevel={highestAcceptanceLevel}
        />
        <Layout.Header
          style={{ background: "#fff", borderBottom: "1px solid #e5e7eb" }}
        >
          <Space>
            <Typography.Text strong>连接状态</Typography.Text>
            <Typography.Text>
              {socket.connected
                ? "connected"
                : socket.stale
                  ? "stale"
                  : "disconnected"}
            </Typography.Text>
            <Typography.Text>轮询可用，WebSocket 可兜底</Typography.Text>
            {socket.lastEvent && (
              <Typography.Text>
                last: {socket.lastEvent.event_type}
              </Typography.Text>
            )}
          </Space>
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>
          <DashboardRoutes />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
