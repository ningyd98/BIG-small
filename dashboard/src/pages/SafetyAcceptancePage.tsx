import {
  Alert,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import {
  useDashboardAcceptance,
  useRecordSafetyReviewNoteMutation,
} from "../api/queries";
import type {
  DashboardSafetyReviewNoteRequest,
  DashboardSafetyReviewNoteResponse,
} from "../api/types";

export function SafetyAcceptancePage() {
  const acceptance = useDashboardAcceptance();
  const [form] = Form.useForm<DashboardSafetyReviewNoteRequest>();
  const reviewMutation = useRecordSafetyReviewNoteMutation();
  const [reviewResult, setReviewResult] =
    useState<DashboardSafetyReviewNoteResponse | null>(null);

  const handleReview = async (values: DashboardSafetyReviewNoteRequest) => {
    const result = await reviewMutation.mutateAsync({
      note: values.note,
      related_evidence_id: values.related_evidence_id || "",
    });
    setReviewResult(result);
    form.resetFields();
  };

  if (acceptance.isLoading) {
    return <Spin aria-label="正在加载安全验收" />;
  }
  if (acceptance.isError || !acceptance.data) {
    return <Card>安全验收数据暂不可用</Card>;
  }

  const snapshot = acceptance.data;
  const levels = snapshot.levels ?? [];
  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="安全验收">
        <Space wrap>
          <Typography.Text strong>
            当前级别：{snapshot.current_level}
          </Typography.Text>
          <Typography.Text>下一等级：{snapshot.next_level}</Typography.Text>
          <Tag color={snapshot.hardware_motion_allowed ? "green" : "red"}>
            硬件运动：{snapshot.hardware_motion_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag color={snapshot.validation_claimed ? "green" : "gold"}>
            验收声明：{String(snapshot.validation_claimed)}
          </Tag>
        </Space>
        {(snapshot.blocked_reasons ?? []).length > 0 && (
          <ul className="plain-list compact-list">
            {(snapshot.blocked_reasons ?? []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </Card>
      <Collapse
        items={levels.map((level) => ({
          key: level.level,
          label: `${level.level} ${level.locked ? "LOCKED" : "OPEN"}`,
          children: (
            <Space orientation="vertical">
              <Typography.Text>{level.definition}</Typography.Text>
              <Typography.Text>
                prerequisite={String(level.prerequisite_complete)} evidence=
                {String(level.evidence_complete)}
              </Typography.Text>
              {(level.blockers ?? []).map((blocker) => (
                <Tag key={blocker} color="gold">
                  {blocker}
                </Tag>
              ))}
            </Space>
          ),
        }))}
      />
      <Card title="安全复核备注">
        {reviewMutation.isError && (
          <Alert
            type="error"
            showIcon
            message={
              reviewMutation.error instanceof Error
                ? reviewMutation.error.message
                : "review note rejected"
            }
            style={{ marginBottom: 16 }}
          />
        )}
        <Form<DashboardSafetyReviewNoteRequest>
          form={form}
          layout="vertical"
          onFinish={handleReview}
          initialValues={{ note: "", related_evidence_id: "" }}
        >
          <Form.Item
            name="note"
            label="安全复核备注"
            rules={[{ required: true, min: 1, max: 1000 }]}
          >
            <Input.TextArea
              aria-label="安全复核备注"
              rows={4}
              maxLength={1000}
            />
          </Form.Item>
          <Form.Item name="related_evidence_id" label="关联证据 ID">
            <Input />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={reviewMutation.isPending}
          >
            提交复核备注
          </Button>
        </Form>
        {reviewResult && (
          <Space orientation="vertical" style={{ marginTop: 16 }}>
            <Typography.Text>复核记录：{reviewResult.note_id}</Typography.Text>
            <Typography.Text>
              硬件运动授权：
              {String(reviewResult.hardware_motion_authorized)}
            </Typography.Text>
          </Space>
        )}
      </Card>
    </Space>
  );
}
