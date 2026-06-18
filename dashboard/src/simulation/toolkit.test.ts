// 前端单元测试，验证 API、WebSocket 或仿真工具行为。
import { describe, expect, it, vi } from "vitest";

import { ScenarioCatalogService } from "./services/ScenarioCatalogService";
import { ExperimentConfigBuilder } from "./builders/ExperimentConfigBuilder";
import { SweepPlanBuilder } from "./builders/SweepPlanBuilder";
import { BatchPlanBuilder } from "./builders/BatchPlanBuilder";
import { RunMonitorService } from "./services/RunMonitorService";
import { MetricsService } from "./services/MetricsService";
import { ComparisonService } from "./services/ComparisonService";
import { ReproductionService } from "./services/ReproductionService";
import { ExportService } from "./services/ExportService";
import { EventTimelineAssembler } from "./services/EventTimelineAssembler";
import { AttemptHistoryService } from "./services/AttemptHistoryService";
import { QueueMonitorService } from "./services/QueueMonitorService";
import { RecoveryStatusService } from "./services/RecoveryStatusService";
import { WorkerHealthService } from "./services/WorkerHealthService";
import type { ScenarioDefinition } from "./domain/ScenarioDefinition";
import type { SimulationMetric } from "./domain/RunMetric";

const scenarios: ScenarioDefinition[] = Array.from(
  { length: 15 },
  (_, index) => ({
    scenario_id: `S${String(index + 1).padStart(2, "0")}_SCENARIO`,
    description: index === 6 ? "Network degradation case" : "Scenario",
    category: index === 6 ? "NETWORK" : index === 13 ? "SAFETY" : "NORMAL",
    fault_types:
      index === 6
        ? ["NETWORK_DEGRADED"]
        : index === 13
          ? ["EMERGENCY_STOP"]
          : [],
    initial_world_state: { target_visible: true },
    scheduled_faults:
      index === 13
        ? [
            {
              fault_id: "f-estop",
              fault_type: "EMERGENCY_STOP",
              trigger_time_ms: 600,
            },
          ]
        : [],
    expected_invariants: ["SafetyShield is not bypassed"],
    allowed_result_statuses: index === 13 ? ["SAFETY_STOPPED"] : ["SUCCESS"],
    forbidden_result_statuses: ["TIMEOUT"],
    maximum_virtual_duration_ms: 30000,
    backend_support: {
      MOCK: "READY",
      MUJOCO: "READY",
      ISAAC_SIM: "BLOCKED_BY_ENV",
      MOVEIT_DRY_RUN: "NOT_CONFIGURED",
    },
  }),
);

const metrics: SimulationMetric[] = [
  {
    name: "completion_time",
    value: 100,
    unit: "ms",
    source: "ExperimentRunner",
    aggregation: "single",
    sample_count: 1,
    backend: "MOCK",
    scenario: "S01_SCENARIO",
    seed: 1,
    control_mode: "PCSC",
  },
  {
    name: "completion_time",
    value: 120,
    unit: "ms",
    source: "ExperimentRunner",
    aggregation: "single",
    sample_count: 1,
    backend: "MOCK",
    scenario: "S01_SCENARIO",
    seed: 1,
    control_mode: "ETEAC",
  },
  {
    name: "task_success",
    value: true,
    unit: "",
    source: "ExperimentRunner",
    aggregation: "single",
    sample_count: 1,
    backend: "MOCK",
    scenario: "S01_SCENARIO",
    seed: 1,
    control_mode: "PCSC",
  },
];

describe("Phase 11 simulation toolkit", () => {
  it("loads 15 scenarios and filters by network category/fault", () => {
    const catalog = new ScenarioCatalogService(scenarios);

    expect(catalog.all()).toHaveLength(15);
    expect(catalog.search("network")[0].scenario_id).toBe("S07_SCENARIO");
    expect(catalog.filter({ category: "SAFETY" })[0].fault_types).toEqual([
      "EMERGENCY_STOP",
    ]);
    expect(
      catalog.detail("S14_SCENARIO")?.scheduled_faults[0].trigger_time_ms,
    ).toBe(600);
  });

  it("builds immutable experiment drafts and rejects shell/path/env extras", () => {
    const builder = ExperimentConfigBuilder.create()
      .backend("MOCK")
      .scenario("S01_SCENARIO")
      .controlMode("PCSC")
      .seed(42)
      .network({ base_latency_ms: 20, jitter_ms: 3, packet_loss: 0.01 });

    const draft = builder.build();

    expect(draft.backend).toBe("MOCK");
    expect(draft.scenarios).toEqual(["S01_SCENARIO"]);
    expect(builder.seed(43).build().seeds).toEqual([43]);
    expect(draft.seeds).toEqual([42]);
    expect(() => builder.parameterOverride("shell", "/bin/sh").build()).toThrow(
      /forbidden/i,
    );
  });

  it("calculates sweep Cartesian products and blocks oversized plans", () => {
    const plan = SweepPlanBuilder.create({ maxRuns: 20 })
      .scenarios(["S01_SCENARIO", "S07_SCENARIO"])
      .modes(["PCSC", "ETEAC"])
      .seeds([0, 1])
      .latencies([20, 40])
      .build();

    expect(plan.totalRuns).toBe(16);
    expect(plan.combinations[0].scenario).toBe("S01_SCENARIO");
    expect(() =>
      SweepPlanBuilder.create({ maxRuns: 4 })
        .scenarios(["S01_SCENARIO", "S07_SCENARIO"])
        .modes(["PCSC", "ETEAC"])
        .seeds([0, 1])
        .latencies([20])
        .build(),
    ).toThrow(/exceeds/i);
  });

  it("builds batch manifests for mode comparison and paired backend runs", () => {
    const modeBatch = BatchPlanBuilder.modeComparison({
      scenario: "S01_SCENARIO",
      seed: 0,
      backend: "MOCK",
    });
    const paired = BatchPlanBuilder.backendPairedRun({
      scenario: "S01_SCENARIO",
      seed: 0,
      leftBackend: "MUJOCO",
      rightBackend: "ISAAC_SIM",
    });

    expect(modeBatch.run_type).toBe("MODE_COMPARISON");
    expect(modeBatch.control_modes).toEqual(["PCSC", "ETEAC", "AUTO"]);
    expect(paired.run_type).toBe("PAIRED_BACKEND");
    expect(paired.paired_key).toBe("S01_SCENARIO:0");
  });

  it("deduplicates stream events, detects gaps, reconnects and marks stale", () => {
    const monitor = new RunMonitorService({ staleAfterMs: 1000 });

    monitor.ingest({ sequence: 1, event_type: "run_state", run_id: "run-1" });
    monitor.ingest({ sequence: 1, event_type: "run_state", run_id: "run-1" });
    monitor.ingest({
      sequence: 3,
      event_type: "metric_update",
      run_id: "run-1",
    });

    expect(monitor.eventsFor("run-1")).toHaveLength(2);
    expect(monitor.sequenceGapDetected()).toBe(true);
    expect(monitor.reconnectMessage()).toEqual({ last_sequence: 3 });
    expect(monitor.isStale(Date.now() + 2000)).toBe(true);
  });

  it("assembles timeline and summarizes metric units", () => {
    const timeline = EventTimelineAssembler.assemble([
      {
        sequence: 1,
        event_type: "fault_injected",
        virtual_time_ms: 600,
        source: "runner",
      },
      {
        sequence: 2,
        event_type: "SafetyShield allow/reject",
        virtual_time_ms: 650,
        source: "shield",
      },
    ]);
    const summary = new MetricsService(metrics).summary();

    expect(timeline[0].label).toContain("fault");
    expect(summary.units.completion_time).toBe("ms");
    expect(summary.sampleCounts.completion_time).toBe(2);
    expect(summary.blockedByEnv).toBe(false);
  });

  it("computes comparison statistics and paired backend alignment", () => {
    const comparison = new ComparisonService(metrics);
    const stats = comparison.compareModes("PCSC", "ETEAC", "completion_time");

    expect(stats.paired_delta).toBe(20);
    expect(stats.relative_delta).toBe(0.2);
    expect(
      comparison.pairedBackendAligned([
        {
          backend: "MUJOCO",
          scenario: "S01_SCENARIO",
          seed: 1,
          paired_key: "a",
        },
        {
          backend: "ISAAC_SIM",
          scenario: "S01_SCENARIO",
          seed: 1,
          paired_key: "a",
        },
      ]),
    ).toBe(true);
  });

  it("warns on reproducibility mismatches and redacts exports", () => {
    const reproduction = new ReproductionService({
      source_commit: "abc",
      source_tree_hash: "tree-a",
      config_hash: "cfg",
      environment_hash: "env-a",
      backend: "MOCK",
      scenario: "S01_SCENARIO",
      seed: 1,
      control_mode: "PCSC",
    });
    const result = reproduction.validate({
      source_commit: "abc",
      source_tree_hash: "tree-b",
      config_hash: "cfg",
      environment_hash: "env-b",
      backend: "MOCK",
      scenario: "S01_SCENARIO",
      seed: 1,
      control_mode: "PCSC",
    });
    const exported = new ExportService().manifestJson({
      path: "/home/alice/project/artifact.json",
      token: "secret",
      controller_config: { ip: "192.168.0.10" },
    });

    expect(result.exact).toBe(false);
    expect(result.warnings).toContain("source_tree_hash mismatch");
    expect(exported).not.toContain("/home/alice");
    expect(exported).not.toContain("secret");
    expect(exported).not.toContain("192.168.0.10");
  });

  it("calls simulation API with role headers and no arbitrary runner name", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ run_id: "run-1" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const draft = ExperimentConfigBuilder.create()
      .backend("MOCK")
      .scenario("S01_SCENARIO")
      .controlMode("PCSC")
      .seed(1)
      .build();
    const { ExperimentSubmissionService } =
      await import("./services/ExperimentSubmissionService");

    await new ExperimentSubmissionService().submit(draft);

    const firstCall = fetchMock.mock.calls[0];
    if (!firstCall) throw new Error("fetch was not called");
    const [url, init] = firstCall as unknown as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("/api/v1/simulation/runs");
    expect(init.method).toBe("POST");
    expect(headers.get("x-dashboard-role")).toBe("EXPERIMENT_OPERATOR");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("runner_name");
  });

  it("summarizes runtime queue workers attempts and recovery", () => {
    const queue = new QueueMonitorService({
      queued: 2,
      running: 1,
      blocked: 1,
      max_queued_jobs: 500,
      max_batch_runs: 120,
    });
    const workers = new WorkerHealthService([
      {
        worker_id: "mock-worker-1",
        backend: "MOCK",
        status: "BUSY",
        active_job_id: "job-1",
        lease_id: "lease-1",
      },
      {
        worker_id: "mujoco-worker-1",
        backend: "MUJOCO",
        status: "IDLE",
        active_job_id: "",
        lease_id: "",
      },
    ]);
    const attempts = new AttemptHistoryService([
      {
        attempt: 1,
        worker_id: "mock-worker-1",
        started_at: "2026-06-18T00:00:00Z",
        ended_at: null,
        result: "RUNNING",
        error: "",
        artifact_paths: {},
      },
    ]);
    const recovery = new RecoveryStatusService({
      recovered_jobs: ["job-2"],
      interrupted_jobs: ["job-3"],
      incomplete_artifacts: [],
      rerun_started: false,
    });

    expect(queue.isNearCapacity()).toBe(false);
    expect(queue.summary()).toContain("2 queued");
    expect(workers.busyCount()).toBe(1);
    expect(workers.backends()).toEqual(["MOCK", "MUJOCO"]);
    expect(attempts.latest()?.result).toBe("RUNNING");
    expect(recovery.hasBlockers()).toBe(false);
    expect(recovery.summary()).toContain("1 recovered");
  });
});
