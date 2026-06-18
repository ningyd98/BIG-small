import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
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

// 安全验收页允许记录复核备注，但硬件运动授权仍只能来自后端安全门。
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
  const level0 = snapshot.level0_read_only;
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
      {level0 && (
        <Card title={level0.mode_label}>
          <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2, lg: 3 }}
              items={[
                {
                  key: "controller",
                  label: "控制器",
                  children: level0.controller_state,
                },
                {
                  key: "estop",
                  label: "E-Stop",
                  children: level0.emergency_stop_state,
                },
                {
                  key: "fault",
                  label: "故障",
                  children: level0.fault_state,
                },
                {
                  key: "mode",
                  label: "模式",
                  children: level0.operation_mode,
                },
                {
                  key: "joint",
                  label: "关节 freshness",
                  children: level0.joint_state_freshness,
                },
                {
                  key: "tcp",
                  label: "TCP freshness",
                  children: level0.tcp_pose_freshness,
                },
                {
                  key: "robot",
                  label: "机器人 identity hash",
                  children: level0.robot_identity_hash || "UNAVAILABLE",
                },
                {
                  key: "config",
                  label: "配置 hash",
                  children: level0.config_hash || "UNAVAILABLE",
                },
                {
                  key: "session",
                  label: "现场 session",
                  children: level0.site_session_id || "UNAVAILABLE",
                },
                {
                  key: "evidence",
                  label: "证据完整性",
                  children: String(level0.evidence_complete),
                },
                {
                  key: "writes",
                  label: "写操作计数",
                  children: String(level0.write_operation_count ?? 0),
                },
                {
                  key: "motion",
                  label: "机械臂位移",
                  children: String(level0.hardware_motion_observed ?? false),
                },
              ]}
            />
            <Space wrap>
              {Object.entries(level0.checks ?? {}).map(([key, passed]) => (
                <Tag key={key} color={passed ? "green" : "gold"}>
                  {key}:{String(passed)}
                </Tag>
              ))}
            </Space>
            {(level0.blockers ?? []).length > 0 && (
              <ul className="plain-list compact-list">
                {(level0.blockers ?? []).map((blocker) => (
                  <li key={blocker}>{blocker}</li>
                ))}
              </ul>
            )}
          </Space>
        </Card>
      )}
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
