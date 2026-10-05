// 研究记录、软件统计和独立物理验收分别展示，所有分配保留在表格及 JSON 中。
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import { useSearchParams } from "react-router-dom";

import {
  researchResultsApi,
  type ResearchRunView,
} from "../api/researchResultsApi";

function count(value: number | null | undefined): string {
  return value == null ? "N/A" : String(value);
}

function statistic(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "N/A";
  const rounded = value.toFixed(3);
  return Number(rounded) === value ? rounded : String(value);
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function counts(values: Record<string, number> | undefined): string {
  return (
    Object.entries(values ?? {})
      .map(([key, value]) => `${key}: ${value}`)
      .join(" · ") || "未记录"
  );
}

function rate(value: number | null | undefined): string {
  return value == null ? "未记录（N/A）" : statistic(value);
}

export function ResearchEvidenceSummary({ view }: { view: ResearchRunView }) {
  const effects = view.effects ?? {};
  const sourceMissing = view.source_missing ?? [];
  const family = view.primary_family ?? {};
  const hypotheses = Array.isArray(family.hypotheses)
    ? family.hypotheses.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const names = [...new Set([...hypotheses, ...Object.keys(effects)])];
  const adjusted = record(family.holm_adjusted_p);
  const rows = names.map((name) => ({ name, values: record(effects[name]) }));
  const timeline = view.timeline;

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title={`研究证据 · ${view.run_id}`}>
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Alert
            type="info"
            title={`实际研究：${view.actual_research_status ?? "NOT_RUN"}`}
            description={`记录范围：${view.scope}。软件诊断通过仅说明数值规则；独立物理来源尚未验收。`}
          />
          <Typography.Text>
            正式验收：{String(view.formal_accepted)} · 独立物理结果计数：
            {count(view.physical_success)}
          </Typography.Text>
          <Typography.Text>
            {count(view.paired_group_denominator)} 组配对 /{" "}
            {count(view.assigned_denominator)} 条全部分配
          </Typography.Text>
          <Typography.Text>
            冻结 N：{count(view.selected_n)} · 覆盖状态：{view.coverage_status}
          </Typography.Text>
          <Typography.Text>
            协议 hash：
            <Typography.Text code>
              {view.protocol_hash ?? "N/A（来源缺失）"}
            </Typography.Text>
          </Typography.Text>
          <Typography.Text>
            全部终止状态：{counts(view.terminal_status_counts)}
          </Typography.Text>
          {sourceMissing.length > 0 && (
            <Alert
              type="warning"
              title={`缺失来源：${sourceMissing.join("、")}`}
            />
          )}
          {(view.reasons ?? []).map((reason, index) => (
            <Typography.Text key={index}>{reason}</Typography.Text>
          ))}
          <a href={researchResultsApi.exportUrl(view.run_id)}>
            导出同分母 JSON
          </a>
        </Space>
      </Card>

      <Card title="目标判定与统计">
        <Typography.Paragraph>
          原始 95% CI 与 Holm 校正 p
          分列；缺失检验仍属于冻结假设族，不能据软件诊断声明实际收益。
        </Typography.Paragraph>
        <Table
          rowKey="goal_id"
          pagination={false}
          dataSource={view.goals ?? []}
          columns={[
            { title: "目标", dataIndex: "goal_id" },
            {
              title: "软件诊断",
              render: (_, goal) => (
                <Tag>软件诊断：{goal.diagnostic_status}</Tag>
              ),
            },
            {
              title: "实际研究",
              render: (_, goal) => `实际研究：${goal.actual_status}`,
            },
            { title: "来源范围", dataIndex: "evidence_scope" },
            {
              title: "依据",
              render: (_, goal) => (goal.reasons ?? []).join("；"),
            },
          ]}
        />
        <Table
          rowKey="name"
          pagination={false}
          dataSource={rows}
          scroll={{ x: 780 }}
          columns={[
            { title: "指标", dataIndex: "name" },
            {
              title: "点估计 [原始 95% 区间]",
              render: (_, row) =>
                `${statistic(row.values.point)} [${statistic(row.values.lower95)}, ${statistic(row.values.upper95)}]`,
            },
            {
              title: "单侧 95% 界",
              render: (_, row) =>
                `[${statistic(row.values.one_sided_lower95)}, ${statistic(row.values.one_sided_upper95)}]`,
            },
            {
              title: "原始 p",
              render: (_, row) => statistic(row.values.p_value),
            },
            {
              title: "Holm 校正 p",
              render: (_, row) =>
                statistic(row.values.adjusted_p_value ?? adjusted[row.name]),
            },
            {
              title: "配对组分母",
              render: (_, row) =>
                typeof row.values.denominator === "number"
                  ? count(row.values.denominator)
                  : "N/A",
            },
            {
              title: "计算来源",
              render: (_, row) =>
                typeof row.values.method === "string"
                  ? row.values.method
                  : "N/A",
            },
          ]}
        />
      </Card>

      <Card title="方法分母、角色成本与诊断">
        {(view.methods ?? []).length === 0 ? (
          <Empty description="方法记录未提供" />
        ) : (
          (view.methods ?? []).map((method) => (
            <Card
              key={method.method_id}
              size="small"
              title={method.method_id}
              style={{ marginBottom: 12 }}
            >
              <Space orientation="vertical">
                <Typography.Text>
                  全部分配：{method.assigned_denominator} ·{" "}
                  {counts(method.terminal_status_counts)}
                </Typography.Text>
                <Typography.Text>
                  云请求合计: {method.cloud_requests_total} · 角色：
                  {counts(method.model_requests_by_role)}
                </Typography.Text>
                <Typography.Text>
                  应用层字节: {method.application_bytes_total} B · 惩罚后 P95:{" "}
                  {count(method.penalized_duration_p95_s)} s
                </Typography.Text>
                <Typography.Text>
                  条件 UNKNOWN：{rate(method.unknown_condition_rate)} ·
                  分母为全部条件判断，未提供来源时不以 episode 替代
                </Typography.Text>
                <Typography.Text>
                  决策 fallback：{rate(method.fallback_decision_rate)} ·
                  分母为全部决策轮次，未提供来源时不以 episode 替代
                </Typography.Text>
                <Typography.Text>
                  附加 episode 指标：UNKNOWN {rate(method.unknown_episode_rate)}{" "}
                  · fallback {rate(method.fallback_episode_rate)} · 无进展终止{" "}
                  {rate(method.no_progress_rate)}
                </Typography.Text>
                <Typography.Text>
                  方法分层：
                  {counts(view.strata_counts_by_method?.[method.method_id])}
                </Typography.Text>
                <Typography.Text>
                  成本范围：{method.metric_scope} · provider 版本：
                  {JSON.stringify(method.provider_versions ?? [])}
                </Typography.Text>
              </Space>
            </Card>
          ))
        )}
      </Card>

      <Card title="候选、接受、启动与独立结果">
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Typography.Text>
            时间线来源：{timeline?.status ?? "NOT_RECORDED"}
          </Typography.Text>
          <Typography.Text>
            候选：{count(timeline?.candidate_count)}
          </Typography.Text>
          <Typography.Text>
            接受：{count(timeline?.accepted_count)}
          </Typography.Text>
          <Typography.Text>
            启动：{count(timeline?.started_count)}
          </Typography.Text>
          <Typography.Text>
            独立物理结果：{count(timeline?.independent_physical_success)}
          </Typography.Text>
          <Typography.Text>
            规则评分不等于概率；缺失概率保持 N/A，规则分数不能充当校准风险。
          </Typography.Text>
          <Typography.Text>
            规则评分：
            {timeline?.rule_scores == null
              ? "N/A（未记录）"
              : JSON.stringify(timeline.rule_scores)}
          </Typography.Text>
          <Typography.Text>
            候选概率：
            {timeline?.candidate_probabilities == null
              ? "N/A（未记录）"
              : JSON.stringify(timeline.candidate_probabilities)}
          </Typography.Text>
          <Table
            rowKey="stage"
            pagination={false}
            dataSource={view.stages ?? []}
            columns={[
              { title: "阶段", dataIndex: "stage" },
              {
                title: "声明状态",
                render: (_, stage) => counts(stage.declared_status_counts),
              },
              { title: "来源核验", dataIndex: "source_validation_status" },
              { title: "已独立接受计数", dataIndex: "accepted_count" },
            ]}
          />
        </Space>
      </Card>

      <Card title={`全部未独立验收记录（${(view.failures ?? []).length}）`}>
        <Typography.Paragraph>
          保留 FAILED、BLOCKED、UNKNOWN 等全部分配；分页仅改变显示，JSON
          导出保留完整记录。
        </Typography.Paragraph>
        <Table
          rowKey="assignment_id"
          dataSource={view.failures ?? []}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 700 }}
          columns={[
            { title: "分配 ID", dataIndex: "assignment_id" },
            { title: "组", dataIndex: "group_id" },
            { title: "方法", dataIndex: "method_id" },
            { title: "终止状态", dataIndex: "status" },
            {
              title: "原因",
              render: (_, failure) => failure.reason ?? "未记录",
            },
          ]}
        />
      </Card>

      <Card title="同一响应的完整 JSON">
        <pre
          data-testid="research-view-json"
          style={{ margin: 0, maxHeight: 360, overflow: "auto" }}
        >
          {JSON.stringify(view, null, 2)}
        </pre>
      </Card>
    </Space>
  );
}

export function ResearchEvidencePage() {
  const [params, setParams] = useSearchParams();
  const runId = params.get("run_id") ?? "";
  const runs = useQuery({
    queryKey: ["research-runs"],
    queryFn: ({ signal }) => researchResultsApi.runs(signal),
    retry: false,
  });
  const evidence = useQuery({
    queryKey: ["research-evidence", runId],
    queryFn: ({ signal }) => researchResultsApi.evidence(runId, signal),
    enabled: runId.length > 0,
    retry: false,
  });
  const selectRun = (value: string) =>
    setParams(value ? { run_id: value } : {});

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Card title="研究结果与证据">
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Typography.Text>
            实际研究：NOT_RUN。读取已登记的产物，不启动实验。
          </Typography.Text>
          <Select
            aria-label="已登记研究记录"
            placeholder="选择已登记记录"
            value={runId || undefined}
            options={(runs.data?.runs ?? []).map((run) => ({
              value: run.run_id,
              label: `${run.run_id} · ${run.scope}`,
            }))}
            onChange={selectRun}
            style={{ width: "100%" }}
          />
          <Input.Search
            aria-label="研究运行 ID"
            placeholder="已登记的运行 ID"
            enterButton="读取证据"
            onSearch={(value) => selectRun(value.trim())}
          />
          {runs.error && (
            <Alert
              type="error"
              title={`记录列表不可用：${runs.error.message}`}
            />
          )}
          {!runs.isLoading &&
            !runs.error &&
            (runs.data?.runs ?? []).length === 0 && (
              <Empty description="暂无已登记研究记录；实际研究 NOT_RUN" />
            )}
        </Space>
      </Card>
      {evidence.isLoading && (
        <Spin tip="读取完整研究来源">
          <div style={{ minHeight: 80 }} />
        </Spin>
      )}
      {evidence.error && (
        <Alert type="error" title={`证据未载入：${evidence.error.message}`} />
      )}
      {evidence.data && <ResearchEvidenceSummary view={evidence.data} />}
    </Space>
  );
}
