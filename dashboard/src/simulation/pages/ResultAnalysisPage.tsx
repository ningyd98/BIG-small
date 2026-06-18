// 结果分析页面，展示指标卡、图表、artifact 和复现实验入口。
import { Card, Empty, Table } from "antd";

import { useSimulationRuns } from "../api/simulationQueries";
import { MetricChart } from "../components/MetricChart";

export function ResultAnalysisPage() {
  const runs = useSimulationRuns();
  const labels = (runs.data?.runs ?? []).map((run) => run.run_id);
  const values = (runs.data?.runs ?? []).map((run) =>
    run.status === "SUCCEEDED" ? 1 : 0,
  );
  return (
    <Card title="Result Analysis">
      {labels.length ? (
        <>
          <MetricChart title="Task success" labels={labels} values={values} />
          <Table
            rowKey="run_id"
            dataSource={runs.data?.runs ?? []}
            columns={[
              { title: "Run", dataIndex: "run_id" },
              { title: "Status", dataIndex: "status" },
              { title: "Backend", dataIndex: "backend" },
            ]}
          />
        </>
      ) : (
        <Empty description="No simulation metrics yet" />
      )}
    </Card>
  );
}
