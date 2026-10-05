import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ResearchRunView } from "../api/researchResultsApi";
import {
  ResearchEvidencePage,
  ResearchEvidenceSummary,
} from "./ResearchEvidencePage";

beforeEach(() => {
  // jsdom has no pseudo-element styles; keep real computed styles for Ant tables.
  const computedStyle = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    computedStyle(element),
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function view(): ResearchRunView {
  return {
    run_id: "fixture-run",
    status: "SOFTWARE_ONLY",
    scope: "SOFTWARE_ONLY",
    actual_research_status: "NOT_RUN",
    formal_accepted: false,
    physical_success: 0,
    protocol_hash: "a".repeat(64),
    selected_n: 600,
    assigned_denominator: 4200,
    paired_group_denominator: 600,
    coverage_status: "COMPLETE",
    strata_counts_by_method: { JOINT: { STATIC_RTT0: 50 } },
    terminal_status_counts: { BLOCKED: 4000, FAILED: 100, UNKNOWN: 100 },
    methods: [
      {
        method_id: "JOINT",
        assigned_denominator: 600,
        cloud_requests_total: 4,
        model_requests_by_role: { PLANNER: 3, JUDGE: 1 },
        application_bytes_total: 100,
        penalized_duration_p95_s: 120,
        unknown_episode_rate: 0.5,
        unknown_condition_rate: null,
        fallback_episode_rate: 0.25,
        fallback_decision_rate: null,
        no_progress_rate: 0.2,
        terminal_status_counts: { BLOCKED: 600 },
        provider_versions: [],
        metric_scope: "DECLARED_SOURCE_BOUND_DIAGNOSTIC",
      },
    ],
    goals: [
      {
        goal_id: "G2",
        diagnostic_status: "PASS",
        actual_status: "NOT_RUN",
        evidence_scope: "SOFTWARE_ONLY",
        estimate: null,
        reasons: ["software fixture"],
      },
    ],
    effects: {
      G2_REQUESTS: {
        point: 0.4,
        lower95: 0.1,
        upper95: 0.6,
        p_value: 0.001,
        adjusted_p_value: 0.005,
        denominator: 600,
        method: "SOFTWARE_ONLY",
        one_sided_lower95: 0.15,
        one_sided_upper95: 0.55,
      },
    },
    primary_family: {},
    stages: ["CAPTURE", "PLANNING", "EXECUTION"].map((stage) => ({
      stage,
      declared_status_counts: { NOT_EXECUTED: 4200 },
      source_validation_status: "NOT_RUN",
      accepted_count: 0,
    })),
    timeline: {
      status: "NOT_RECORDED",
      candidate_count: null,
      accepted_count: null,
      started_count: null,
      independent_physical_success: 0,
      rule_scores: null,
      candidate_probabilities: null,
    },
    failures: [
      {
        assignment_id: "g1::JOINT",
        group_id: "g1",
        method_id: "JOINT",
        status: "BLOCKED",
        reason: "SOURCE_NOT_ACCEPTED",
      },
    ],
    source_missing: [],
    reasons: ["independent raw physical source verifier is not integrated"],
  };
}

describe("research evidence", () => {
  it("shows separate software planning and physical evidence without success badge", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(screen.getAllByText(/SOFTWARE_ONLY/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/实际研究.*NOT_RUN/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NOT_EXECUTED/).length).toBeGreaterThan(0);
    expect(screen.queryByText("物理成功")).not.toBeInTheDocument();
    expect(screen.queryByText("研究验收通过")).not.toBeInTheDocument();
  });

  it("renders original point interval paired denominator protocol and blocked records", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(screen.getByText("0.400 [0.100, 0.600]")).toBeInTheDocument();
    expect(
      screen.getByText("600 组配对 / 4200 条全部分配"),
    ).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("g1::JOINT")).toBeInTheDocument();
    expect(screen.getByText("SOURCE_NOT_ACCEPTED")).toBeInTheDocument();
    expect(screen.getAllByText(/BLOCKED/).length).toBeGreaterThan(0);
  });

  it("keeps unknown condition and fallback decision denominators missing", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(screen.getByText(/条件 UNKNOWN.*未记录/)).toBeInTheDocument();
    expect(screen.getByText(/决策 fallback.*未记录/)).toBeInTheDocument();
    expect(screen.getByText(/规则评分.*概率/)).toBeInTheDocument();
    expect(screen.getByText("候选：N/A")).toBeInTheDocument();
    expect(screen.getByText(/接受.*N\/A/)).toBeInTheDocument();
    expect(screen.getByText(/启动.*N\/A/)).toBeInTheDocument();
  });

  it("exports JSON through the same allowed run identity", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(
      screen.getByRole("link", { name: "导出同分母 JSON" }),
    ).toHaveAttribute("href", "/api/v1/research/runs/fixture-run/export");
  });

  it("keeps raw confidence intervals and Holm p separate from goal acceptance", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(screen.getByText(/原始 95% CI/)).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Holm 校正 p" }),
    ).toBeInTheDocument();
    expect(screen.getByText("0.005")).toBeInTheDocument();
    expect(screen.getByText(/FAILED: 100/)).toBeInTheDocument();
    expect(screen.getByText(/UNKNOWN: 100/)).toBeInTheDocument();
    expect(screen.getByText(/软件诊断.*PASS/)).toBeInTheDocument();
  });

  it("includes remote JUDGE in cloud role costs and keeps byte and time units", () => {
    render(<ResearchEvidenceSummary view={view()} />);
    expect(screen.getByText(/JUDGE: 1/)).toBeInTheDocument();
    expect(screen.getByText(/PLANNER: 3/)).toBeInTheDocument();
    expect(screen.getByText(/云请求合计: 4/)).toBeInTheDocument();
    expect(screen.getByText(/应用层字节: 100 B/)).toBeInTheDocument();
    expect(screen.getByText(/惩罚后 P95: 120 s/)).toBeInTheDocument();
  });

  it("shows missing sources with N/A denominators rather than zero successes", () => {
    const missing = {
      ...view(),
      status: "NOT_RUN" as const,
      scope: "UNVERIFIED" as const,
      protocol_hash: null,
      assigned_denominator: null,
      paired_group_denominator: null,
      methods: [],
      effects: {},
      stages: [],
      failures: [],
      source_missing: ["records", "protocol"],
    };
    render(<ResearchEvidenceSummary view={missing} />);
    expect(screen.getByText("N/A 组配对 / N/A 条全部分配")).toBeInTheDocument();
    expect(screen.getByText(/缺失来源.*records.*protocol/)).toBeInTheDocument();
    expect(
      screen.queryByText("0 组配对 / 0 条全部分配"),
    ).not.toBeInTheDocument();
  });

  it("preserves the full loaded view in the inspectable JSON including failed records", () => {
    const record = view();
    render(<ResearchEvidenceSummary view={record} />);
    const raw = JSON.parse(
      screen.getByTestId("research-view-json").textContent ?? "",
    );
    expect(raw).toEqual(record);
  });

  it("reports an artifact rejection without displaying a fabricated result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        text: async () => "research_artifact_invalid",
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/simulation/research?run_id=rejected"]}>
          <ResearchEvidencePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      (await screen.findAllByText(/research_artifact_invalid/)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("研究验收通过")).not.toBeInTheDocument();
    expect(screen.queryByTestId("research-view-json")).not.toBeInTheDocument();
  });
});
