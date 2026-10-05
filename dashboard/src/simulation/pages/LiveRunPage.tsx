// 实时运行页面，展示队列、worker、lease、attempt、取消和超时状态。
import { Button, Card, Empty, Space, Table, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";

import { StatusBadge } from "../../components/StatusBadge";
import {
  useCancelSimulationRun,
  useRetrySimulationRun,
  useSimulationRunAttempts,
  useSimulationRuns,
  useSimulationRuntimeHealth,
  useSimulationRuntimeQueue,
  useSimulationRuntimeWorkers,
} from "../api/simulationQueries";
import { AttemptHistory } from "../components/AttemptHistory";
import { CancellationProgress } from "../components/CancellationProgress";
import { LeaseStatus } from "../components/LeaseStatus";
import { QueueStatusPanel } from "../components/QueueStatusPanel";
import { RuntimeHealthCard } from "../components/RuntimeHealthCard";
import { WorkerStatusPanel } from "../components/WorkerStatusPanel";
import { VisualRunEvidence } from "../components/VisualRunEvidence";
import { simulationApi } from "../api/simulationApi";

export function LiveRunPage() {
  const runs = useSimulationRuns();
  const health = useSimulationRuntimeHealth();
  const queue = useSimulationRuntimeQueue();
  const workers = useSimulationRuntimeWorkers();
  const cancel = useCancelSimulationRun();
  const retry = useRetrySimulationRun();
  const selectedRun = runs.data?.runs[0];
  const attempts = useSimulationRunAttempts(selectedRun?.run_id ?? "");
  const evidenceEvents = useQuery({
    queryKey: ["simulation", selectedRun?.run_id, "events"],
    enabled: Boolean(selectedRun),
    queryFn: () => simulationApi.runEvents(selectedRun!.run_id),
    refetchInterval: 2000,
  });
  const evidence: Record<string, unknown> = {
    evaluation_scope: selectedRun?.manifest.normalized_config.execution_scope ?? "UNKNOWN",
    task_execution: "NOT_EXECUTED",
  };
  for (const event of evidenceEvents.data?.events ?? []) {
    const payload = event.payload ?? {};
    if (payload.layer === "INDEPENDENT_PHYSICAL_RESULT" && payload.result
      && typeof payload.result === "object") {
      evidence.physical_success = (payload.result as Record<string, unknown>).success;
    }
    if (payload.layer === "ONLINE_VERIFICATION" && payload.event
      && typeof payload.event === "object") {
      const decision = payload.event as Record<string, unknown>;
      if (decision.kind === "RESULT_VERIFIED") {
        evidence.online_reported_complete = decision.verification_status === "PASS"
          && payload.route === "CONTINUE";
      }
    }
    if ((payload.layer === "SKILL_RETURN" || payload.layer === "PARTIAL_SKILL_RETURN")
      && Number(payload.physics_steps) > 0) {
      evidence.task_execution = "EXECUTED";
    }
  }
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <div className="simulation-workbench-grid">
        <RuntimeHealthCard health={health.data} />
        <QueueStatusPanel queue={queue.data} />
      </div>
      <WorkerStatusPanel workers={workers.data?.workers ?? []} />
      <Card title="Live Run Monitor">
        <Table
          rowKey="run_id"
          loading={runs.isLoading}
          dataSource={runs.data?.runs ?? []}
          locale={{
            emptyText: <Empty description="No active simulation runs" />,
          }}
          columns={[
            { title: "Run", dataIndex: "run_id" },
            {
              title: "Status",
              dataIndex: "status",
              render: (status: string) => <StatusBadge status={status} />,
            },
            { title: "Scenario", dataIndex: "scenario_id" },
            { title: "Mode", dataIndex: "control_mode" },
            { title: "Backend", dataIndex: "backend" },
            { title: "Worker", dataIndex: "worker_id" },
            {
              title: "Actions",
              render: (_, run) => (
                <Space>
                  <Button
                    size="small"
                    onClick={() => cancel.mutate(run.run_id)}
                    disabled={[
                      "SUCCEEDED",
                      "FAILED",
                      "CANCELLED",
                      "TIMED_OUT",
                      "BLOCKED_BY_ENV",
                    ].includes(run.status)}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="small"
                    onClick={() => retry.mutate(run.run_id)}
                    disabled={
                      !["FAILED", "TIMED_OUT", "CANCELLED"].includes(run.status)
                    }
                  >
                    Retry
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Card title="Selected Run Runtime">
        <LeaseStatus run={selectedRun} />
        <CancellationProgress run={selectedRun} />
      </Card>
      <AttemptHistory attempts={attempts.data?.attempts ?? []} />
      {selectedRun?.manifest.normalized_config.input_mode === "RGBD"
        && <VisualRunEvidence result={evidence} />}
      <Card title="Runtime Channels">
        <Typography.Text>
          WebSocket stream uses persisted sequence replay, heartbeat and polling
          fallback.
        </Typography.Text>
      </Card>
    </Space>
  );
}
