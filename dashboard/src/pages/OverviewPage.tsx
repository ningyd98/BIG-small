// 概览页面：集中展示项目权威状态、硬件声明和最新 evidence，不在前端推导结论。
import { Card, Col, Empty, Row, Space, Spin, Typography } from "antd";

import { useDashboardSummary } from "../api/queries";
import type { DashboardSummary } from "../api/types";
import { BlockerList } from "../components/BlockerList";
import { ProvenanceCard } from "../components/ProvenanceCard";
import { SafetyGateCard } from "../components/SafetyGateCard";
import { StatusBadge } from "../components/StatusBadge";

// 概览页集中展示权威状态、硬件边界和最新证据，不在前端推导验收结论。
type OverviewPageViewProps = {
  summary: DashboardSummary;
};

export function OverviewPageView({ summary }: OverviewPageViewProps) {
  const blockers = summary.blockers ?? [];
  const latestEvidence = summary.latest_evidence ?? [];
  const reasonCodes = summary.safety_summary.reason_codes ?? [];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space orientation="vertical" size="middle">
          <Typography.Title level={2} style={{ margin: 0 }}>
            {summary.current_project_status}
          </Typography.Title>
          <Space wrap>
            <Typography.Text strong>
              真实机械臂验证：{summary.real_robot_validation}
            </Typography.Text>
            <Typography.Text strong>
              最高硬件级别：{summary.highest_acceptance_level}
            </Typography.Text>
            <Typography.Text>
              硬件声明：{summary.hardware_claim}
            </Typography.Text>
            <Typography.Text>
              状态来源：{summary.current_project_status_source}
            </Typography.Text>
          </Space>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <SafetyGateCard
            hardwareMotionAuthorized={
              summary.safety_summary.hardware_motion_authorized ?? false
            }
            reasonCodes={reasonCodes}
          />
        </Col>
        <Col xs={24} lg={12}>
          <ProvenanceCard
            commit={summary.software_commit}
            sourceTreeHash={summary.source_tree_hash}
            worktreeClean={summary.worktree_clean ?? false}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="阻塞项" size="small">
            <BlockerList blockers={blockers} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="最新证据" size="small">
            {latestEvidence.length === 0 ? (
              <Empty
                description="暂无证据"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <ul className="plain-list compact-list">
                {latestEvidence.map((record) => (
                  <li key={record.evidence_id}>
                    <Space wrap>
                      <Typography.Text>{record.phase}</Typography.Text>
                      <StatusBadge status={record.status} />
                      <Typography.Text>{record.relative_path}</Typography.Text>
                    </Space>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  );
}

export function OverviewPage() {
  const query = useDashboardSummary();
  if (query.isLoading) {
    return <Spin aria-label="正在加载概览" />;
  }
  if (query.isError || !query.data) {
    return <Card>控制台汇总暂不可用</Card>;
  }
  return <OverviewPageView summary={query.data} />;
}
