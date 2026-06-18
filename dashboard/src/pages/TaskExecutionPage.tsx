// 任务执行页面：展示任务运行状态和只读 evidence，不向浏览器暴露机器人执行入口。
import { Card, Descriptions, Empty, Space, Spin, Table, Tag } from "antd";

import { useDashboardRuntime, useDashboardSummary } from "../api/queries";

// 任务执行页展示运行配置和活动实验，不提供控制器启用、轨迹发送或真实硬件入口。
export function TaskExecutionPage() {
  const runtime = useDashboardRuntime();
  const summary = useDashboardSummary();

  if (runtime.isLoading || summary.isLoading) {
    return <Spin aria-label="正在加载任务执行数据" />;
  }

  if (runtime.isError || summary.isError || !runtime.data || !summary.data) {
    return <Card>任务执行数据暂不可用</Card>;
  }

  const activeExperiments = summary.data.active_experiments ?? [];
  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="任务执行">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="运行配置">
            {runtime.data.runtime_profile}
          </Descriptions.Item>
          <Descriptions.Item label="后端就绪">
            {runtime.data.backend_readiness.map((item) => (
              <Tag key={item.name} color="blue">
                {item.name}:{item.status}
              </Tag>
            ))}
          </Descriptions.Item>
          <Descriptions.Item label="环境阻塞">
            {(runtime.data.environment_blockers ?? []).join(", ") || "-"}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="活动实验">
        <Table
          rowKey="experiment_id"
          dataSource={activeExperiments}
          locale={{
            emptyText: <Empty description="当前没有运行中的任务" />,
          }}
          columns={[
            { title: "实验", dataIndex: "experiment_id" },
            { title: "状态", dataIndex: "status" },
            { title: "硬件声明", dataIndex: "hardware_claim" },
            {
              title: "阻塞项",
              dataIndex: "blockers",
              render: (value: string[] | undefined) =>
                (value ?? []).join(", ") || "-",
            },
          ]}
        />
      </Card>
    </Space>
  );
}
