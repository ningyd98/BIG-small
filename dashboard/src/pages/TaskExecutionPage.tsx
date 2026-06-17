import { Card, Descriptions, Empty } from "antd";

export function TaskExecutionPage() {
  return (
    <Card title="任务执行">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="访问模式">只读</Descriptions.Item>
        <Descriptions.Item label="禁止操作">
          跳过步骤、强制完成、任意命令、直接控制机器人、编辑计划
        </Descriptions.Item>
      </Descriptions>
      <Empty description="当前没有运行中的任务。仿真实验的暂停和取消必须通过后端任务管理器。" />
    </Card>
  );
}
