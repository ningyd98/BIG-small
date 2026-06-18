import { Button, Card, Empty, Space, Table, Typography } from "antd";

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

export function LiveRunPage() {
  const runs = useSimulationRuns();
  const health = useSimulationRuntimeHealth();
  const queue = useSimulationRuntimeQueue();
  const workers = useSimulationRuntimeWorkers();
  const cancel = useCancelSimulationRun();
  const retry = useRetrySimulationRun();
  const selectedRun = runs.data?.runs[0];
  const attempts = useSimulationRunAttempts(selectedRun?.run_id ?? "");
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
      <Card title="Runtime Channels">
        <Typography.Text>
          WebSocket stream uses persisted sequence replay, heartbeat and polling
          fallback.
        </Typography.Text>
      </Card>
    </Space>
  );
}
