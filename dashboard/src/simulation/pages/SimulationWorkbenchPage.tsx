import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";

import { StatusBadge } from "../../components/StatusBadge";
import { usePlannerRuntime } from "../../modelControl/api/modelControlQueries";
import { ExperimentConfigBuilder } from "../builders/ExperimentConfigBuilder";
import {
  useSimulationCapabilities,
  useSimulationRuntimeHealth,
  useSimulationRuntimeQueue,
  useSimulationRuns,
  useSimulationScenarios,
  useSubmitSimulationRun,
} from "../api/simulationQueries";
import { QueueStatusPanel } from "../components/QueueStatusPanel";
import { RuntimeHealthCard } from "../components/RuntimeHealthCard";
import type { ExperimentDraft } from "../domain/ExperimentDraft";

type FormValues = {
  backend: "MOCK" | "MUJOCO" | "ISAAC_SIM" | "MOVEIT_DRY_RUN";
  scenario: string;
  controlMode: "PCSC" | "ETEAC" | "AUTO";
  seed: number;
  latency: number;
  jitter: number;
  packetLoss: number;
  repetitions: number;
  description: string;
};

export function SimulationWorkbenchPage() {
  const [error, setError] = useState("");
  const [form] = Form.useForm<FormValues>();
  const capabilities = useSimulationCapabilities();
  const scenarios = useSimulationScenarios();
  const runs = useSimulationRuns();
  const runtimeHealth = useSimulationRuntimeHealth();
  const runtimeQueue = useSimulationRuntimeQueue();
  const plannerRuntime = usePlannerRuntime();
  const submit = useSubmitSimulationRun();
  const scenarioItems = useMemo(
    () => scenarios.data?.scenarios ?? [],
    [scenarios.data?.scenarios],
  );
  const backendItems = useMemo(
    () => capabilities.data?.backends ?? [],
    [capabilities.data?.backends],
  );

  const initialValues: FormValues = {
    backend: "MOCK",
    scenario: scenarioItems[0]?.scenario_id ?? "S01_NORMAL_STATIC",
    controlMode: "PCSC",
    seed: 0,
    latency: 40,
    jitter: 5,
    packetLoss: 0,
    repetitions: 1,
    description: "",
  };

  const readinessByBackend = useMemo(() => {
    return Object.fromEntries(backendItems.map((item) => [item.backend, item]));
  }, [backendItems]);

  const handleSubmit = async (values: FormValues) => {
    const normalized = { ...initialValues, ...values };
    setError("");
    try {
      const draft: ExperimentDraft = ExperimentConfigBuilder.create()
        .backend(normalized.backend)
        .scenario(normalized.scenario)
        .controlMode(normalized.controlMode)
        .seed(normalized.seed)
        .repetitions(normalized.repetitions)
        .network({
          base_latency_ms: normalized.latency,
          jitter_ms: normalized.jitter,
          packet_loss: normalized.packetLoss,
        })
        .build();
      await submit.mutateAsync({
        ...draft,
        description: normalized.description,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "submit rejected");
    }
  };

  const selectedBackend =
    Form.useWatch("backend", form) ?? initialValues.backend;
  const backendReadiness = readinessByBackend[selectedBackend];
  const blockers = backendReadiness?.blockers ?? [];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        BIG-small Simulation Workbench
      </Typography.Title>
      <Alert
        type="info"
        showIcon
        title="仿真工作台仅运行 Mock、MuJoCo、Isaac 环境检查和 MoveIt dry-run 只读规划证据；不连接真实控制器。"
      />
      {error && <Alert type="error" showIcon title={error} />}

      <div className="simulation-workbench-grid">
        <Card title="实验设计" size="small">
          <Form<FormValues>
            form={form}
            layout="vertical"
            initialValues={initialValues}
            onFinish={handleSubmit}
          >
            <Form.Item
              label="Backend"
              name="backend"
              rules={[{ required: true }]}
            >
              <Select
                options={backendItems.map((backend) => ({
                  value: backend.backend,
                  label: `${backend.backend} (${backend.readiness})`,
                }))}
              />
            </Form.Item>
            <Form.Item
              label="Scenario"
              name="scenario"
              rules={[{ required: true }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={scenarioItems.map((scenario) => ({
                  value: scenario.scenario_id,
                  label: `${scenario.scenario_id} ${scenario.category}`,
                }))}
              />
            </Form.Item>
            <Form.Item
              label="Mode"
              name="controlMode"
              rules={[{ required: true }]}
            >
              <Select
                options={["PCSC", "ETEAC", "AUTO"].map((mode) => ({
                  value: mode,
                  label: mode,
                }))}
              />
            </Form.Item>
            <Form.Item label="Seed" name="seed" rules={[{ required: true }]}>
              <InputNumber min={0} precision={0} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="Description" name="description">
              <Input maxLength={160} />
            </Form.Item>
          </Form>
        </Card>

        <Card title="参数与网络" size="small">
          <Form form={form} layout="vertical">
            <Form.Item label="Latency ms" name="latency">
              <InputNumber min={0} max={60000} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="Jitter ms" name="jitter">
              <InputNumber min={0} max={60000} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="Packet loss" name="packetLoss">
              <InputNumber
                min={0}
                max={1}
                step={0.01}
                style={{ width: "100%" }}
              />
            </Form.Item>
            <Form.Item label="Repetitions" name="repetitions">
              <InputNumber min={1} max={100} style={{ width: "100%" }} />
            </Form.Item>
          </Form>
        </Card>

        <Card title="提交与阻塞" size="small">
          <Space orientation="vertical" style={{ width: "100%" }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Readiness">
                <StatusBadge
                  status={backendReadiness?.readiness ?? "UNKNOWN"}
                />
              </Descriptions.Item>
              <Descriptions.Item label="Queued">
                {runtimeQueue.data?.queued ?? 0}
              </Descriptions.Item>
              <Descriptions.Item label="Hardware writes">
                none
              </Descriptions.Item>
            </Descriptions>
            {blockers.length ? (
              blockers.map((blocker) => <Tag key={blocker}>{blocker}</Tag>)
            ) : (
              <Empty
                description="无 backend blocker"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
            <Button
              type="primary"
              onClick={() => form.submit()}
              loading={submit.isPending}
              disabled={submit.isPending}
            >
              Submit simulation run
            </Button>
          </Space>
        </Card>
      </div>

      <div className="simulation-workbench-grid">
        <RuntimeHealthCard health={runtimeHealth.data} />
        <QueueStatusPanel queue={runtimeQueue.data} />
        <Card title="Planner Configuration" size="small">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="Provider">
              {plannerRuntime.data?.active_provider ?? "MOCK"}
            </Descriptions.Item>
            <Descriptions.Item label="Model">
              {plannerRuntime.data?.active_model ?? "mock"}
            </Descriptions.Item>
            <Descriptions.Item label="Health">
              <StatusBadge status={plannerRuntime.data?.health ?? "READY"} />
            </Descriptions.Item>
            <Descriptions.Item label="Profile version">
              {plannerRuntime.data?.config_version ?? 0}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>

      <Card title="Active and recent runs">
        <Table
          rowKey="run_id"
          loading={runs.isLoading}
          dataSource={runs.data?.runs ?? []}
          columns={[
            { title: "Run", dataIndex: "run_id" },
            { title: "Backend", dataIndex: "backend" },
            { title: "Scenario", dataIndex: "scenario_id" },
            { title: "Mode", dataIndex: "control_mode" },
            { title: "Seed", dataIndex: "seed" },
            { title: "Worker", dataIndex: "worker_id" },
            { title: "Attempt", dataIndex: "attempt" },
            {
              title: "Status",
              dataIndex: "status",
              render: (status: string) => <StatusBadge status={status} />,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
