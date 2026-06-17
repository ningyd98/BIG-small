import {
  Alert,
  Button,
  Card,
  Form,
  InputNumber,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { useState } from "react";

import {
  useCancelExperimentMutation,
  useDashboardCapabilities,
  useDashboardExperiments,
  useStartExperimentMutation,
} from "../api/queries";
import type {
  DashboardExperimentCreateRequest,
  DashboardExperimentJob,
} from "../api/types";
import { StatusBadge } from "../components/StatusBadge";

const experimentKinds = [
  { value: "MOCK_SOFTWARE", label: "Mock 软件实验" },
  { value: "MUJOCO_SMOKE", label: "MuJoCo Smoke" },
  { value: "SYNTHETIC_DRY_RUN", label: "Synthetic Dry-Run" },
  { value: "MOVEIT_RUNTIME_DRY_RUN", label: "MoveIt Runtime Dry-Run" },
];

const controlModes = [
  { value: "PCSC", label: "PCSC" },
  { value: "ETEAC", label: "ETEAC" },
  { value: "AUTO", label: "AUTO" },
];

const terminalStatuses = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "BLOCKED_BY_ENV",
]);

export function SimulationLabPage() {
  const [form] = Form.useForm<DashboardExperimentCreateRequest>();
  const [error, setError] = useState("");
  const capabilities = useDashboardCapabilities("EXPERIMENT_OPERATOR");
  const experiments = useDashboardExperiments();
  const startMutation = useStartExperimentMutation();
  const cancelMutation = useCancelExperimentMutation();
  const writesAllowed = Boolean(
    capabilities.data?.allowed_write_operations?.includes(
      "start_software_experiment",
    ),
  );

  const handleStart = async (values: DashboardExperimentCreateRequest) => {
    setError("");
    try {
      await startMutation.mutateAsync(values);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "experiment start rejected",
      );
    }
  };

  const handleCancel = async (experimentId: string) => {
    setError("");
    try {
      await cancelMutation.mutateAsync(experimentId);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "experiment cancel rejected",
      );
    }
  };

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="仿真实验">
        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 16 }}
          />
        )}
        <Form<DashboardExperimentCreateRequest>
          form={form}
          layout="vertical"
          initialValues={{
            kind: "MOCK_SOFTWARE",
            scenario_id: "S01_NORMAL_STATIC",
            seed: 0,
            control_mode: "PCSC",
            network_profile: "NORMAL",
            fault_profile: "none",
            repetitions: 1,
          }}
          onFinish={handleStart}
          disabled={!writesAllowed || startMutation.isPending}
        >
          <Form.Item name="kind" label="后端" rules={[{ required: true }]}>
            <Select options={experimentKinds} />
          </Form.Item>
          <Form.Item
            name="scenario_id"
            label="场景"
            rules={[{ required: true, min: 1 }]}
          >
            <Select
              options={[
                { value: "S01_NORMAL_STATIC", label: "S01_NORMAL_STATIC" },
                { value: "S14_EMERGENCY_STOP", label: "S14_EMERGENCY_STOP" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="control_mode"
            label="控制模式"
            rules={[{ required: true }]}
          >
            <Select options={controlModes} />
          </Form.Item>
          <Form.Item name="seed" label="随机种子" rules={[{ required: true }]}>
            <InputNumber min={0} precision={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="repetitions"
            label="重复次数"
            rules={[{ required: true }]}
          >
            <InputNumber
              min={1}
              max={100}
              precision={0}
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={startMutation.isPending}
          >
            启动安全软件实验
          </Button>
        </Form>
        {!writesAllowed && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
            当前后端未允许写操作；提交仍会由后端权限再次判定。
          </Typography.Paragraph>
        )}
      </Card>
      <Card title="实验队列">
        <Table<DashboardExperimentJob>
          rowKey="experiment_id"
          loading={experiments.isLoading}
          dataSource={experiments.data?.jobs ?? []}
          expandable={{
            expandedRowRender: (record) => (
              <Space orientation="vertical" style={{ width: "100%" }}>
                <Typography.Text>
                  Evidence: {record.evidence_path || record.evidence_id || "-"}
                </Typography.Text>
                <Typography.Text>
                  Exit code: {record.exit_code ?? "-"}
                </Typography.Text>
                <Typography.Text>
                  Blockers: {(record.blockers ?? []).join(", ") || "-"}
                </Typography.Text>
                <Typography.Text code style={{ whiteSpace: "pre-wrap" }}>
                  {record.stdout || record.stderr || "no logs yet"}
                </Typography.Text>
              </Space>
            ),
          }}
          columns={[
            { title: "ID", dataIndex: "experiment_id" },
            { title: "类型", dataIndex: "kind" },
            {
              title: "状态",
              dataIndex: "status",
              render: (status: string) => <StatusBadge status={status} />,
            },
            { title: "场景", dataIndex: "scenario_id" },
            { title: "模式", dataIndex: "control_mode" },
            { title: "硬件声明", dataIndex: "hardware_claim" },
            {
              title: "操作",
              render: (_, record) => (
                <Button
                  danger
                  disabled={terminalStatuses.has(record.status)}
                  loading={cancelMutation.isPending}
                  onClick={() => void handleCancel(record.experiment_id)}
                >
                  取消
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
