import { Card, Space, Tag, Typography } from "antd";

export function VisualRunEvidence({ result }: { result: Record<string, unknown> }) {
  const scope = String(result.evaluation_scope ?? "UNKNOWN");
  const physical = result.physical_success;
  const online = result.online_reported_complete;
  const execution = String(result.task_execution ?? "NOT_EXECUTED");
  const yesNo = (value: unknown) => value === true ? "是" : value === false ? "否" : "UNKNOWN";
  return <Card title="视觉与物理证据">
    <Space wrap><Tag>{scope}</Tag><Tag>{execution}</Tag></Space>
    <Typography.Paragraph>在线完成声明：{yesNo(online)}</Typography.Paragraph>
    <Typography.Paragraph>独立物理成功：{yesNo(physical)}</Typography.Paragraph>
    <Typography.Text type="secondary">UNKNOWN 与未执行阶段不计为成功。最终成功还需独立任务语义与全部验收条件通过。</Typography.Text>
  </Card>;
}
