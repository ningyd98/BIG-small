// 批量实验页面，展示矩阵、并发、取消和重试入口。
import { Button, Card, InputNumber, Select, Space, Typography } from "antd";
import { useState } from "react";

import { BatchPlanBuilder } from "../builders/BatchPlanBuilder";
import { SweepPlanBuilder } from "../builders/SweepPlanBuilder";
import {
  useCancelSimulationBatch,
  useRetryFailedSimulationBatch,
  useSimulationRuntimeQueue,
} from "../api/simulationQueries";
import { QueueStatusPanel } from "../components/QueueStatusPanel";
import { ResourceUsagePanel } from "../components/ResourceUsagePanel";

export function BatchExperimentPage() {
  const [seedCount, setSeedCount] = useState(3);
  const [batchId, setBatchId] = useState("");
  const queue = useSimulationRuntimeQueue();
  const cancelBatch = useCancelSimulationBatch();
  const retryFailed = useRetryFailedSimulationBatch();
  const sweep = SweepPlanBuilder.create({ maxRuns: 120 })
    .scenarios(["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED"])
    .modes(["PCSC", "ETEAC", "AUTO"])
    .seeds(Array.from({ length: seedCount }, (_, index) => index))
    .latencies([20, 40, 80])
    .build();
  const modeManifest = BatchPlanBuilder.modeComparison({
    scenario: "S01_NORMAL_STATIC",
    seed: 0,
    backend: "MOCK",
  });

  return (
    <Card title="Batch and Sweep">
      <Space orientation="vertical" style={{ width: "100%" }}>
        <Select
          value="Full Matrix"
          options={[
            { value: "Single Run", label: "Single Run" },
            { value: "Scenario Batch", label: "Scenario Batch" },
            { value: "Seed Batch", label: "Seed Batch" },
            { value: "Mode Comparison", label: "Mode Comparison" },
            { value: "Backend Paired Run", label: "Backend Paired Run" },
            { value: "Full Matrix", label: "Full Matrix" },
          ]}
          style={{ width: 260 }}
        />
        <InputNumber
          value={seedCount}
          min={1}
          max={10}
          onChange={(value) => setSeedCount(value ?? 1)}
        />
        <Typography.Text>Total sweep runs: {sweep.totalRuns}</Typography.Text>
        <Typography.Text>
          Mode manifest: {modeManifest.control_modes.join(", ")}
        </Typography.Text>
        <InputNumber
          placeholder="Batch suffix"
          value={batchId ? Number(batchId.replace(/\D/g, "")) : null}
          onChange={(value) =>
            setBatchId(value === null ? "" : `batch-${value}`)
          }
        />
        <Space>
          <Button type="primary">Queue batch manifest</Button>
          <Button
            disabled={!batchId}
            onClick={() => cancelBatch.mutate(batchId)}
          >
            Cancel batch
          </Button>
          <Button
            disabled={!batchId}
            onClick={() => retryFailed.mutate(batchId)}
          >
            Retry failed
          </Button>
        </Space>
        <QueueStatusPanel queue={queue.data} />
        <ResourceUsagePanel queue={queue.data} />
      </Space>
    </Card>
  );
}
