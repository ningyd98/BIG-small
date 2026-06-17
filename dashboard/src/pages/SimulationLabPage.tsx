import {
  Button,
  Card,
  Form,
  InputNumber,
  Select,
  Space,
  Typography,
} from "antd";

import { useDashboardCapabilities } from "../api/queries";

export function SimulationLabPage() {
  const capabilities = useDashboardCapabilities();
  const writesAllowed = Boolean(
    capabilities.data?.allowed_write_operations?.length,
  );

  return (
    <Card title="仿真实验">
      <Typography.Paragraph>
        该页面只启动后端 allowlist 中的软件实验。不会接收 shell、脚本路径、ROS
        topic 或真实控制器地址。
      </Typography.Paragraph>
      <Form layout="vertical" disabled={!writesAllowed}>
        <Form.Item label="后端">
          <Select
            value="MOCK_SOFTWARE"
            options={[
              { value: "MOCK_SOFTWARE", label: "Mock 软件实验" },
              { value: "MUJOCO_SOFTWARE", label: "MuJoCo 软件实验" },
              { value: "SYNTHETIC_DRY_RUN", label: "Synthetic Dry-Run" },
              {
                value: "MOVEIT_RUNTIME_DRY_RUN",
                label: "MoveIt Runtime Dry-Run",
              },
            ]}
          />
        </Form.Item>
        <Form.Item label="场景">
          <Select
            value="S01_NORMAL_STATIC"
            options={[
              { value: "S01_NORMAL_STATIC", label: "S01_NORMAL_STATIC" },
            ]}
          />
        </Form.Item>
        <Form.Item label="随机种子">
          <InputNumber value={0} min={0} />
        </Form.Item>
        <Space>
          <Button type="primary" disabled={!writesAllowed}>
            启动安全软件实验
          </Button>
          <Button disabled={!writesAllowed}>取消软件实验</Button>
        </Space>
      </Form>
      {!writesAllowed && (
        <Typography.Paragraph type="secondary">
          当前后端 capabilities 未允许写操作；按钮禁用只是 UI
          表达，后端仍会再次拒绝。
        </Typography.Paragraph>
      )}
    </Card>
  );
}
