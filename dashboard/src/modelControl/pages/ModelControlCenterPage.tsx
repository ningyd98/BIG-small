// AI 模型控制中心主页面，集中管理 Planner profile、Ollama 模型和 dry-run。
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import {
  useActivateModelProfile,
  useActivateOllamaModel,
  useCreateModelProfile,
  useModelCapabilities,
  useModelDownloads,
  useModelProfiles,
  useOllamaModels,
  useOllamaStatus,
  usePlannerDryRun,
  usePlannerRuntime,
  useSmallModelCatalog,
  useStartModelDownload,
} from "../api/modelControlQueries";
import type {
  LocalModel,
  ModelProviderProfile,
  PlannerProviderKind,
  SmallModelCatalogItem,
} from "../api/modelControlApi";

type ProfileForm = {
  display_name: string;
  provider_kind: PlannerProviderKind;
  base_url: string;
  chat_completions_path: string;
  model_name: string;
  api_key?: string;
};

export function ModelControlCenterPage() {
  const capabilities = useModelCapabilities();
  const profiles = useModelProfiles();
  const runtime = usePlannerRuntime();
  const ollamaStatus = useOllamaStatus();
  const ollamaModels = useOllamaModels();
  const catalog = useSmallModelCatalog();
  const downloads = useModelDownloads();
  const createProfile = useCreateModelProfile();
  const activateProfile = useActivateModelProfile();
  const startDownload = useStartModelDownload();
  const activateOllama = useActivateOllamaModel();
  const dryRun = usePlannerDryRun();
  const [downloadModel, setDownloadModel] = useState("llama3.2:3b");
  const [dryRunInstruction, setDryRunInstruction] = useState("pick red cube");

  const handleCreateProfile = async (values: ProfileForm) => {
    await createProfile.mutateAsync({
      ...values,
      api_key: values.api_key || undefined,
    });
  };

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        AI 模型控制中心
      </Typography.Title>
      <Alert
        showIcon
        type="info"
        message="Planner dry-run 只生成规划合同预览，dispatch=false，hardware_execution=false。"
      />

      <div className="simulation-workbench-grid">
        <Card title="当前 Planner" size="small">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="Provider">
              <Tag color="blue">{runtime.data?.active_provider ?? "MOCK"}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Model">
              {runtime.data?.active_model ?? "mock"}
            </Descriptions.Item>
            <Descriptions.Item label="Health">
              {runtime.data?.health ?? "READY"}
            </Descriptions.Item>
            <Descriptions.Item label="Config version">
              {runtime.data?.config_version ?? 0}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="Ollama 本地运行时" size="small">
          <Space orientation="vertical" style={{ width: "100%" }}>
            <Tag color={ollamaStatus.data?.reachable ? "green" : "red"}>
              {ollamaStatus.data?.reachable ? "READY" : "BLOCKED"}
            </Tag>
            <Typography.Text>
              Version: {ollamaStatus.data?.version || "unavailable"}
            </Typography.Text>
            <Input
              value={downloadModel}
              onChange={(event) => setDownloadModel(event.target.value)}
              placeholder="精确 Ollama 模型名，例如 llama3.2:3b"
            />
            <Button
              type="primary"
              onClick={() => startDownload.mutate(downloadModel)}
              loading={startDownload.isPending}
            >
              下载模型
            </Button>
          </Space>
        </Card>
      </div>

      <Card title="Provider Profiles" size="small">
        <Form<ProfileForm>
          layout="inline"
          initialValues={{
            provider_kind: "RULE_BASED",
            chat_completions_path: "/v1/chat/completions",
            model_name: "rule-based",
          }}
          onFinish={handleCreateProfile}
        >
          <Form.Item name="display_name" rules={[{ required: true }]}>
            <Input placeholder="Profile 名称" />
          </Form.Item>
          <Form.Item name="provider_kind" rules={[{ required: true }]}>
            <Select
              style={{ width: 180 }}
              options={(
                capabilities.data?.supported_provider_kinds ?? [
                  "MOCK",
                  "RULE_BASED",
                  "OPENAI_COMPATIBLE",
                  "OLLAMA",
                ]
              ).map((kind) => ({ value: kind, label: kind }))}
            />
          </Form.Item>
          <Form.Item name="base_url">
            <Input placeholder="Base URL" />
          </Form.Item>
          <Form.Item name="model_name" rules={[{ required: true }]}>
            <Input placeholder="Model" />
          </Form.Item>
          <Form.Item name="api_key">
            <Input.Password placeholder="API key，不回显已有值" />
          </Form.Item>
          <Button
            htmlType="submit"
            loading={createProfile.isPending}
            data-testid="model-profile-save"
          >
            保存
          </Button>
        </Form>
        <Table<ModelProviderProfile>
          size="small"
          rowKey="profile_id"
          dataSource={profiles.data ?? []}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "display_name" },
            { title: "Provider", dataIndex: "provider_kind" },
            { title: "Model", dataIndex: "model_name" },
            {
              title: "Secret",
              render: (_, row) => (row.secret_present ? "已配置" : "无"),
            },
            {
              title: "操作",
              render: (_, row) => (
                <Button
                  size="small"
                  onClick={() => activateProfile.mutate(row.profile_id)}
                >
                  激活
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="本地模型" size="small">
        <Table<LocalModel>
          size="small"
          rowKey="name"
          dataSource={ollamaModels.data ?? []}
          pagination={false}
          columns={[
            { title: "模型", dataIndex: "name" },
            { title: "大小", render: (_, row) => row.size ?? "大小未知" },
            { title: "更新时间", dataIndex: "modified_at" },
            {
              title: "操作",
              render: (_, row) => (
                <Button
                  size="small"
                  onClick={() => activateOllama.mutate(row.name)}
                >
                  设为当前模型
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="小模型目录" size="small">
        <Table<SmallModelCatalogItem>
          size="small"
          rowKey="catalog_id"
          dataSource={catalog.data ?? []}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "display_name" },
            { title: "Ollama tag", dataIndex: "ollama_model" },
            { title: "Family", dataIndex: "family" },
            {
              title: "参数",
              render: (_, row) =>
                row.parameter_size_b == null
                  ? "未知"
                  : `${row.parameter_size_b}B`,
            },
            {
              title: "大小",
              render: (_, row) =>
                row.estimated_download_bytes == null
                  ? "大小未知"
                  : `${Math.round(row.estimated_download_bytes / 1_000_000)} MB`,
            },
            {
              title: "状态",
              render: (_, row) => (
                <Tag color={row.installed ? "green" : "default"}>
                  {row.installed ? "installed" : "not installed"}
                </Tag>
              ),
            },
            {
              title: "操作",
              render: (_, row) => (
                <Button
                  size="small"
                  disabled={row.installed}
                  onClick={() => startDownload.mutate(row.ollama_model)}
                >
                  下载
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="下载中心" size="small">
        <Space orientation="vertical" style={{ width: "100%" }}>
          {(downloads.data ?? []).map((job) => (
            <div key={job.download_id}>
              <Typography.Text>{job.model_name}</Typography.Text>
              <Progress percent={Math.round(job.progress_ratio * 100)} />
              <Tag>{job.status}</Tag>
            </div>
          ))}
        </Space>
      </Card>

      <Card title="Planner Dry-Run" size="small">
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Input.TextArea
            value={dryRunInstruction}
            onChange={(event) => setDryRunInstruction(event.target.value)}
            rows={3}
          />
          <Button
            type="primary"
            onClick={() =>
              dryRun.mutate({
                user_instruction: dryRunInstruction,
                sample_scene: "S01_NORMAL_STATIC",
                control_mode: "PCSC",
              })
            }
            loading={dryRun.isPending}
          >
            Generate Plan Dry-Run
          </Button>
          {dryRun.data && (
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="dispatch">
                {String(dryRun.data.dispatch)}
              </Descriptions.Item>
              <Descriptions.Item label="hardware_execution">
                {String(dryRun.data.hardware_execution)}
              </Descriptions.Item>
              <Descriptions.Item label="provider">
                {dryRun.data.provider_kind}
              </Descriptions.Item>
              <Descriptions.Item label="raw">
                <Typography.Text code>
                  {dryRun.data.raw_planner_output}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          )}
        </Space>
      </Card>
    </Space>
  );
}
