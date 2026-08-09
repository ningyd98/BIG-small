// Sim2Real 工作台：把现有 MuJoCo 域随机化能力暴露为可视实验设计界面；真实硬件阶段保持锁定。
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Divider,
  InputNumber,
  Select,
  Space,
  Statistic,
  Steps,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "../../components/StatusBadge";
import { ExperimentConfigBuilder } from "../builders/ExperimentConfigBuilder";
import {
  useSimulationCapabilities,
  useSimulationScenarios,
  useSubmitSimulationBatch,
} from "../api/simulationQueries";
import {
  buildSeedSequence,
  buildSim2RealPlan,
  computeSim2RealGap,
  initialSim2RealMeasurements,
  SIM2REAL_AXES,
  SIM2REAL_RANDOMIZATION_SCALE,
  type Sim2RealGapRow,
  type Sim2RealMeasurementMap,
  type Sim2RealRandomizationLevel,
} from "../domain/sim2real";

const RANDOMIZATION_LEVELS: Sim2RealRandomizationLevel[] = [
  "NONE",
  "MILD",
  "MODERATE",
  "SEVERE",
];

function Sim2RealGapChart({
  rows,
  level,
}: {
  rows: Sim2RealGapRow[];
  level: Sim2RealRandomizationLevel;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let chart: {
      dispose: () => void;
      setOption: (option: unknown) => void;
    } | null = null;
    void import("echarts").then((echarts) => {
      if (!ref.current || disposed) return;
      chart = echarts.init(ref.current);
      chart.setOption({
        title: {
          text: "实测偏差与随机化覆盖",
          subtext: "归一化设计图，不是任务成功率或真机实验结果",
          textStyle: { fontSize: 14 },
          subtextStyle: { fontSize: 11 },
        },
        tooltip: { trigger: "axis" },
        legend: { top: 42 },
        grid: { left: 50, right: 20, top: 82, bottom: 55 },
        xAxis: {
          type: "category",
          data: rows.map((row) => row.label),
          axisLabel: { rotate: 15 },
        },
        yAxis: {
          type: "value",
          name: "% full envelope",
          min: 0,
        },
        series: [
          {
            name: "实测偏差",
            type: "bar",
            data: rows.map((row) => Number((row.normalizedGap * 100).toFixed(1))),
          },
          {
            name: `${level} 覆盖半径`,
            type: "line",
            symbol: "circle",
            data: rows.map(() => SIM2REAL_RANDOMIZATION_SCALE[level] * 100),
          },
        ],
      });
    });
    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [level, rows]);

  return <div ref={ref} style={{ width: "100%", height: 330 }} />;
}

function downloadPlan(plan: unknown) {
  const blob = new Blob([JSON.stringify(plan, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = "sim2real_experiment_plan.json";
  anchor.click();
  URL.revokeObjectURL(href);
}

export function Sim2RealWorkbenchPage() {
  const capabilities = useSimulationCapabilities();
  const scenarios = useSimulationScenarios();
  const submitBatch = useSubmitSimulationBatch();

  const [scenario, setScenario] = useState("S01_NORMAL_STATIC");
  const [controlMode, setControlMode] = useState<"PCSC" | "ETEAC" | "AUTO">(
    "AUTO",
  );
  const [level, setLevel] =
    useState<Sim2RealRandomizationLevel>("MODERATE");
  const [seedCount, setSeedCount] = useState(5);
  const [repetitions, setRepetitions] = useState(2);
  const [measurements, setMeasurements] = useState<Sim2RealMeasurementMap>(
    initialSim2RealMeasurements,
  );
  const [calibrationConfirmed, setCalibrationConfirmed] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [lastBatchId, setLastBatchId] = useState("");

  const scenarioItems = useMemo(
    () => scenarios.data?.scenarios ?? [],
    [scenarios.data?.scenarios],
  );
  const seeds = useMemo(() => buildSeedSequence(seedCount), [seedCount]);
  const gapRows = useMemo(
    () => computeSim2RealGap(measurements, level),
    [level, measurements],
  );
  const coveredCount = gapRows.filter((row) => row.covered).length;
  const plan = useMemo(
    () =>
      buildSim2RealPlan({
        scenario,
        controlMode,
        level,
        seedCount,
        repetitions,
        measurements,
      }),
    [controlMode, level, measurements, repetitions, scenario, seedCount],
  );

  const mujocoReadiness = capabilities.data?.backends.find(
    (backend) => backend.backend === "MUJOCO",
  );
  const isaacReadiness = capabilities.data?.backends.find(
    (backend) => backend.backend === "ISAAC_SIM",
  );
  const mujocoReady = mujocoReadiness?.readiness === "READY";

  const matrixRows = useMemo(
    () =>
      seeds.flatMap((seed) =>
        Array.from({ length: repetitions }, (_, repetition) => ({
          key: `${scenario}-${controlMode}-${level}-${seed}-${repetition + 1}`,
          scenario,
          controlMode,
          level,
          seed,
          repetition: repetition + 1,
        })),
      ),
    [controlMode, level, repetitions, scenario, seeds],
  );

  const handleMeasurement = (key: keyof Sim2RealMeasurementMap, value: number) => {
    setMeasurements((current) => ({ ...current, [key]: value }));
    setCalibrationConfirmed(false);
  };

  const applyPreset = (preset: "NOMINAL" | "EDGE_CASE") => {
    if (preset === "NOMINAL") {
      setMeasurements(initialSim2RealMeasurements());
    } else {
      setMeasurements({
        object_mass_kg: 0.18,
        friction_coefficient: 0.42,
        actuator_delay_ms: 55,
        camera_depth_noise_m: 0.012,
      });
    }
    setCalibrationConfirmed(false);
  };

  const handleSubmitBatch = async () => {
    setSubmitError("");
    setLastBatchId("");
    try {
      const draft = ExperimentConfigBuilder.create()
        .backend("MUJOCO")
        .scenario(scenario)
        .controlMode(controlMode)
        .seeds(seeds)
        .repetitions(repetitions)
        .runType("BATCH")
        .domainRandomization(level !== "NONE", level)
        .build();
      const response = await submitBatch.mutateAsync({
        ...draft,
        tags: [...(draft.tags ?? []), "sim2real", `dr:${level}`],
        description: `Sim2Real robustness batch; calibration_confirmed=${calibrationConfirmed}`,
      });
      setLastBatchId(response.batch_id);
    } catch (caught) {
      setSubmitError(
        caught instanceof Error ? caught.message : "Sim2Real batch submit rejected",
      );
    }
  };

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          Sim2Real Workbench
        </Typography.Title>
        <Typography.Text type="secondary">
          系统辨识 → 域随机化 → 配对复现 → promotion gate。当前页面只会提交仿真实验，不开放真实机械臂写操作。
        </Typography.Text>
      </div>

      <Alert
        type="warning"
        showIcon
        title="真实硬件仍保持锁定"
        description="当前仓库权威状态仍是 real_robot_validation=NOT_STARTED。此工作台不会连接真实控制器，不会 servo enable / brake release / trajectory / MoveIt execute。"
      />
      {submitError && <Alert type="error" showIcon title={submitError} />}
      {lastBatchId && (
        <Alert
          type="success"
          showIcon
          title={`MuJoCo Sim2Real batch 已进入现有仿真队列：${lastBatchId}`}
        />
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 16,
        }}
      >
        <Card size="small">
          <Statistic title="随机化覆盖参数" value={`${coveredCount}/4`} />
          <Typography.Text type="secondary">
            仅表示当前手工输入标定值是否落在选定随机化范围内
          </Typography.Text>
        </Card>
        <Card size="small">
          <Statistic title="计划仿真运行数" value={plan.planned_run_count} />
          <Typography.Text type="secondary">
            seeds × repetitions；仍由现有 allowlist worker 执行
          </Typography.Text>
        </Card>
        <Card size="small">
          <Statistic
            title="MuJoCo runtime"
            value={mujocoReadiness?.readiness ?? "UNKNOWN"}
          />
          <Typography.Text type="secondary">Phase 11 runtime 后端</Typography.Text>
        </Card>
        <Card size="small">
          <Statistic
            title="Isaac cross-check"
            value={isaacReadiness?.readiness ?? "UNKNOWN"}
          />
          <Typography.Text type="secondary">
            用于跨仿真后端 sanity check，不冒充真实世界
          </Typography.Text>
        </Card>
      </div>

      <Card title="1. 系统辨识与真实标定输入" size="small">
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            title="默认值来自仿真 nominal，只是编辑起点。请录入称重、摩擦估计、端到端延迟和相机深度噪声的真实测量值后再勾选确认。"
          />
          <Space wrap>
            <Button onClick={() => applyPreset("NOMINAL")}>恢复 nominal</Button>
            <Button onClick={() => applyPreset("EDGE_CASE")}>
              填入界面演示值
            </Button>
            <Tag>source: configs/phase9/domain_randomization.yaml</Tag>
          </Space>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 16,
            }}
          >
            {SIM2REAL_AXES.map((axis) => (
              <Card key={axis.key} size="small" title={axis.label}>
                <Space orientation="vertical" style={{ width: "100%" }}>
                  <InputNumber
                    value={measurements[axis.key]}
                    min={0}
                    step={axis.key === "camera_depth_noise_m" ? 0.001 : 0.01}
                    style={{ width: "100%" }}
                    addonAfter={axis.unit}
                    onChange={(value) =>
                      handleMeasurement(axis.key, Number(value ?? axis.nominal))
                    }
                  />
                  <Typography.Text type="secondary">
                    nominal={axis.nominal}；full envelope=[{axis.min}, {axis.max}]
                  </Typography.Text>
                </Space>
              </Card>
            ))}
          </div>
          <Checkbox
            checked={calibrationConfirmed}
            onChange={(event) => setCalibrationConfirmed(event.target.checked)}
          >
            我确认以上数值来自本轮真实测量/标定，而不是示例值
          </Checkbox>
        </Space>
      </Card>

      <Card title="2. 域随机化与实验矩阵" size="small">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 16,
          }}
        >
          <div>
            <Typography.Text strong>场景</Typography.Text>
            <Select
              value={scenario}
              style={{ width: "100%", marginTop: 8 }}
              showSearch
              optionFilterProp="label"
              options={scenarioItems.map((item) => ({
                value: item.scenario_id,
                label: `${item.scenario_id} ${item.category}`,
              }))}
              onChange={setScenario}
            />
          </div>
          <div>
            <Typography.Text strong>控制模式</Typography.Text>
            <Select
              value={controlMode}
              style={{ width: "100%", marginTop: 8 }}
              options={["PCSC", "ETEAC", "AUTO"].map((item) => ({
                value: item,
                label: item,
              }))}
              onChange={setControlMode}
            />
          </div>
          <div>
            <Typography.Text strong>随机化等级</Typography.Text>
            <Select
              value={level}
              style={{ width: "100%", marginTop: 8 }}
              options={RANDOMIZATION_LEVELS.map((item) => ({
                value: item,
                label: `${item} (${SIM2REAL_RANDOMIZATION_SCALE[item] * 100}% envelope)`,
              }))}
              onChange={setLevel}
            />
          </div>
          <div>
            <Typography.Text strong>Seed 数</Typography.Text>
            <InputNumber
              value={seedCount}
              min={1}
              max={20}
              precision={0}
              style={{ width: "100%", marginTop: 8 }}
              onChange={(value) => setSeedCount(Number(value ?? 1))}
            />
          </div>
          <div>
            <Typography.Text strong>每 seed 重复次数</Typography.Text>
            <InputNumber
              value={repetitions}
              min={1}
              max={20}
              precision={0}
              style={{ width: "100%", marginTop: 8 }}
              onChange={(value) => setRepetitions(Number(value ?? 1))}
            />
          </div>
        </div>

        <Divider />
        <Space wrap>
          <Button onClick={() => downloadPlan(plan)}>导出实验方案 JSON</Button>
          <Button
            type="primary"
            loading={submitBatch.isPending}
            disabled={!mujocoReady || submitBatch.isPending}
            onClick={() => void handleSubmitBatch()}
          >
            提交 MuJoCo 域随机化 Batch
          </Button>
          {!mujocoReady && (
            <Tag color="warning">
              MuJoCo {mujocoReadiness?.readiness ?? "UNKNOWN"}
            </Tag>
          )}
        </Space>

        <Divider />
        <Table
          size="small"
          pagination={{ pageSize: 8 }}
          rowKey="key"
          dataSource={matrixRows}
          columns={[
            { title: "Scenario", dataIndex: "scenario" },
            { title: "Mode", dataIndex: "controlMode" },
            { title: "DR", dataIndex: "level" },
            { title: "Seed", dataIndex: "seed" },
            { title: "Rep", dataIndex: "repetition" },
          ]}
        />
      </Card>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.2fr) minmax(320px, 0.8fr)",
          gap: 16,
        }}
      >
        <Card title="3. Sim2Real gap 可视化" size="small">
          <Sim2RealGapChart rows={gapRows} level={level} />
          <Table
            size="small"
            pagination={false}
            rowKey="key"
            dataSource={gapRows}
            columns={[
              { title: "参数", dataIndex: "label" },
              {
                title: "实测",
                render: (_, row) => `${row.measured} ${row.unit}`,
              },
              {
                title: "当前随机化范围",
                render: (_, row) =>
                  `[${row.selectedMin.toFixed(4)}, ${row.selectedMax.toFixed(4)}]`,
              },
              {
                title: "覆盖",
                render: (_, row) => (
                  <Tag color={row.covered ? "success" : "warning"}>
                    {row.covered ? "COVERED" : "OUTSIDE"}
                  </Tag>
                ),
              },
            ]}
          />
        </Card>

        <Card title="4. Promotion Gate" size="small">
          <Steps
            direction="vertical"
            current={calibrationConfirmed ? 1 : 0}
            items={[
              {
                title: "S0 标定",
                description: calibrationConfirmed
                  ? "真实标定输入已人工确认"
                  : "等待真实测量确认",
                status: calibrationConfirmed ? "finish" : "process",
              },
              {
                title: "S1 域随机化仿真",
                description: "MuJoCo 多 seed / 多重复；输出正式 artifact",
              },
              {
                title: "S2 跨后端复核",
                description: "MuJoCo ↔ Isaac paired evidence，识别 simulator-specific bias",
              },
              {
                title: "S3 真机只读 shadow",
                description: "LOCKED：仅在独立 Level 0 安全审批后允许 joint/camera state 只读采集",
                status: "wait",
              },
              {
                title: "S4 受限真机运动",
                description: "LOCKED：本分支不提供运动 dispatch；必须重新立项和现场验收",
                status: "wait",
              },
            ]}
          />
          <Divider />
          <Descriptions column={1} size="small">
            <Descriptions.Item label="real_controller_contacted">
              <StatusBadge status="FALSE" />
            </Descriptions.Item>
            <Descriptions.Item label="hardware_motion_observed">
              <StatusBadge status="FALSE" />
            </Descriptions.Item>
            <Descriptions.Item label="hardware_write_operations">
              []
            </Descriptions.Item>
            <Descriptions.Item label="real motion dispatch">
              <Tag color="error">DISABLED</Tag>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>

      <Card title="开源工具协同路线" size="small">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="MuJoCo">
            <Tag color="success">当前主执行后端</Tag>
            继续使用现有 domain randomization 与 deterministic seed evidence；后续可用 MjSpec 做结构化参数注入。
          </Descriptions.Item>
          <Descriptions.Item label="Isaac Lab">
            <Tag>可选增强</Tag>
            用 EventManager 做 mass / friction / sensor / disturbance randomization，作为第二仿真后端交叉验证。
          </Descriptions.Item>
          <Descriptions.Item label="Rerun">
            <Tag>可选增强</Tag>
            用于轨迹、相机、深度、关节状态和 sim/real 对齐播放；不承担控制职责。
          </Descriptions.Item>
          <Descriptions.Item label="ECharts">
            <Tag color="success">已复用</Tag>
            当前页面直接使用仓库既有开源图表依赖，不新增前端重量级依赖。
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  );
}
