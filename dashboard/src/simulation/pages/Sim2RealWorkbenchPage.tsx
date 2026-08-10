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

import type { components } from "../../api/generated/schema";
import { StatusBadge } from "../../components/StatusBadge";
import { ExperimentConfigBuilder } from "../builders/ExperimentConfigBuilder";
import {
  useSimulationCapabilities,
  useGenerateSim2RealGapReport,
  useSimulationScenarios,
  useSubmitSimulationBatch,
} from "../api/simulationQueries";
import {
  buildSeedSequence,
  buildSim2RealPlan,
  computeSim2RealGap,
  initialSim2RealMeasurements,
  initialSim2RealParameters,
  SIM2REAL_AXES,
  SIM2REAL_RANDOMIZATION_SCALE,
  type Sim2RealGapRow,
  type Sim2RealAxis,
  type Sim2RealMeasurementMap,
  type Sim2RealParameterConfig,
  type Sim2RealParameterMap,
  type Sim2RealRandomizationLevel,
} from "../domain/sim2real";

type GapReportRequest = components["schemas"]["GapReportRequest"];

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
            data: rows.map((row) =>
              Number((row.normalizedGap * 100).toFixed(1)),
            ),
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

function downloadText(filename: string, value: string, type: string) {
  const href = URL.createObjectURL(new Blob([value], { type }));
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
}

export function Sim2RealWorkbenchPage() {
  const capabilities = useSimulationCapabilities();
  const scenarios = useSimulationScenarios();
  const submitBatch = useSubmitSimulationBatch();
  const generateGapReport = useGenerateSim2RealGapReport();

  const [scenario, setScenario] = useState("S01_NORMAL_STATIC");
  const [controlMode, setControlMode] = useState<"PCSC" | "ETEAC" | "AUTO">(
    "AUTO",
  );
  const [level, setLevel] = useState<Sim2RealRandomizationLevel>("MODERATE");
  const [seedCount, setSeedCount] = useState(5);
  const [repetitions, setRepetitions] = useState(2);
  const [measurements, setMeasurements] = useState<Sim2RealMeasurementMap>(
    initialSim2RealMeasurements,
  );
  const [parameterConfigs, setParameterConfigs] =
    useState<Sim2RealParameterMap>(initialSim2RealParameters);
  const [simulationTrace, setSimulationTrace] = useState<unknown>();
  const [realTrace, setRealTrace] = useState<unknown>();
  const [traceError, setTraceError] = useState("");
  const [calibrationConfirmed, setCalibrationConfirmed] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [lastBatchId, setLastBatchId] = useState("");

  const scenarioItems = useMemo(
    () => scenarios.data?.scenarios ?? [],
    [scenarios.data?.scenarios],
  );
  const seeds = useMemo(() => buildSeedSequence(seedCount), [seedCount]);
  const gapRows = useMemo(
    () => computeSim2RealGap(measurements, level, parameterConfigs),
    [level, measurements, parameterConfigs],
  );
  const enabledCount = gapRows.filter((row) => row.enabled).length;
  const coveredCount = gapRows.filter(
    (row) => row.enabled && row.covered,
  ).length;
  const plan = useMemo(
    () =>
      buildSim2RealPlan({
        scenario,
        controlMode,
        level,
        seedCount,
        repetitions,
        measurements,
        parameters: parameterConfigs,
      }),
    [
      controlMode,
      level,
      measurements,
      parameterConfigs,
      repetitions,
      scenario,
      seedCount,
    ],
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

  const handleMeasurement = (
    key: keyof Sim2RealMeasurementMap,
    value: number,
  ) => {
    setMeasurements((current) => ({ ...current, [key]: value }));
    setCalibrationConfirmed(false);
  };

  const handleParameter = (
    key: keyof Sim2RealParameterMap,
    update: Partial<Sim2RealParameterConfig>,
  ) => {
    setParameterConfigs((current) => ({
      ...current,
      [key]: { ...current[key], ...update },
    }));
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
        joint_damping_scale: 1.2,
        actuator_gain_scale: 0.92,
        gravity_z_m_s2: -9.80665,
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
        .domainRandomization(level !== "NONE", level, parameterConfigs)
        .build();
      const response = await submitBatch.mutateAsync({
        ...draft,
        tags: [...(draft.tags ?? []), "sim2real", `dr:${level}`],
        description: `Sim2Real robustness batch; calibration_confirmed=${calibrationConfirmed}`,
      });
      setLastBatchId(response.batch_id);
    } catch (caught) {
      setSubmitError(
        caught instanceof Error
          ? caught.message
          : "Sim2Real batch submit rejected",
      );
    }
  };

  const loadTrace = async (
    file: File | undefined,
    setter: (value: unknown) => void,
  ) => {
    if (!file) return;
    setTraceError("");
    try {
      setter(JSON.parse(await file.text()) as unknown);
    } catch (caught) {
      setTraceError(
        caught instanceof Error ? caught.message : "Trace JSON 解析失败",
      );
    }
  };

  const handleGapReport = async () => {
    if (!simulationTrace || !realTrace) return;
    setTraceError("");
    try {
      await generateGapReport.mutateAsync({
        simulation: simulationTrace,
        real: realTrace,
        alignment_tolerance_ms: 50,
      } as GapReportRequest);
    } catch (caught) {
      setTraceError(
        caught instanceof Error ? caught.message : "Gap report 生成失败",
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
          系统辨识 → 域随机化 → 配对复现 → promotion
          gate。当前页面只会提交仿真实验，不开放真实机械臂写操作。
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
          <Statistic
            title="随机化覆盖参数"
            value={`${coveredCount}/${enabledCount}`}
          />
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
          <Typography.Text type="secondary">
            Phase 11 runtime 后端
          </Typography.Text>
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
                    min={axis.key === "gravity_z_m_s2" ? undefined : 0}
                    step={axis.key === "camera_depth_noise_m" ? 0.001 : 0.01}
                    style={{ width: "100%" }}
                    addonAfter={axis.unit}
                    onChange={(value) =>
                      handleMeasurement(axis.key, Number(value ?? axis.nominal))
                    }
                  />
                  <Typography.Text type="secondary">
                    nominal={axis.nominal}；full envelope=[{axis.min},{" "}
                    {axis.max}]
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
        <Typography.Title level={5}>Per-parameter 随机化规格</Typography.Title>
        <Alert
          type="info"
          showIcon
          title="同一 seed 先生成一份共享 sample，再分别映射到 MuJoCo MjSpec 与 Isaac Lab EventManager。参数 seed 按参数名派生，因此增删其他参数不会改变已有参数的采样值。"
          style={{ marginBottom: 12 }}
        />
        <Table
          size="small"
          pagination={false}
          scroll={{ x: 1660 }}
          rowKey="key"
          dataSource={SIM2REAL_AXES}
          columns={[
            {
              title: "启用",
              width: 70,
              fixed: "left",
              render: (_, axis: Sim2RealAxis) => (
                <Checkbox
                  checked={parameterConfigs[axis.key].enabled}
                  onChange={(event) =>
                    handleParameter(axis.key, {
                      enabled: event.target.checked,
                    })
                  }
                />
              ),
            },
            {
              title: "参数",
              width: 150,
              fixed: "left",
              render: (_, axis: Sim2RealAxis) => (
                <Space orientation="vertical" size={0}>
                  <Typography.Text strong>{axis.label}</Typography.Text>
                  <Typography.Text type="secondary">{axis.key}</Typography.Text>
                </Space>
              ),
            },
            {
              title: "分布",
              width: 125,
              render: (_, axis: Sim2RealAxis) => (
                <Select
                  value={parameterConfigs[axis.key].distribution}
                  style={{ width: 112 }}
                  options={["UNIFORM", "NORMAL", "FIXED"].map((value) => ({
                    value,
                    label: value,
                  }))}
                  onChange={(distribution) =>
                    handleParameter(axis.key, {
                      distribution,
                      ...(distribution === "NORMAL" &&
                      !parameterConfigs[axis.key].std
                        ? {
                            mean: parameterConfigs[axis.key].nominal,
                            std: Math.max(
                              (parameterConfigs[axis.key].max -
                                parameterConfigs[axis.key].min) /
                                6,
                              0.000001,
                            ),
                          }
                        : {}),
                    })
                  }
                />
              ),
            },
            {
              title: "范围模式",
              width: 145,
              render: (_, axis: Sim2RealAxis) => (
                <Select
                  value={parameterConfigs[axis.key].range_mode}
                  style={{ width: 132 }}
                  options={["LEVEL_SCALED", "ABSOLUTE"].map((value) => ({
                    value,
                    label: value,
                  }))}
                  onChange={(range_mode) =>
                    handleParameter(axis.key, { range_mode })
                  }
                />
              ),
            },
            {
              title: "Nominal",
              width: 120,
              render: (_, axis: Sim2RealAxis) => (
                <InputNumber
                  value={parameterConfigs[axis.key].nominal}
                  style={{ width: 108 }}
                  onChange={(value) =>
                    handleParameter(axis.key, {
                      nominal: Number(value ?? axis.nominal),
                    })
                  }
                />
              ),
            },
            {
              title: "Min",
              width: 120,
              render: (_, axis: Sim2RealAxis) => (
                <InputNumber
                  value={parameterConfigs[axis.key].min}
                  style={{ width: 108 }}
                  onChange={(value) =>
                    handleParameter(axis.key, {
                      min: Number(value ?? axis.min),
                    })
                  }
                />
              ),
            },
            {
              title: "Max",
              width: 120,
              render: (_, axis: Sim2RealAxis) => (
                <InputNumber
                  value={parameterConfigs[axis.key].max}
                  style={{ width: 108 }}
                  onChange={(value) =>
                    handleParameter(axis.key, {
                      max: Number(value ?? axis.max),
                    })
                  }
                />
              ),
            },
            {
              title: "Mean",
              width: 120,
              render: (_, axis: Sim2RealAxis) => {
                const config = parameterConfigs[axis.key];
                return (
                  <InputNumber
                    value={config.mean}
                    disabled={config.distribution !== "NORMAL"}
                    placeholder={String(config.nominal)}
                    style={{ width: 108 }}
                    onChange={(value) =>
                      handleParameter(axis.key, {
                        mean: value == null ? null : Number(value),
                      })
                    }
                  />
                );
              },
            },
            {
              title: "Std",
              width: 120,
              render: (_, axis: Sim2RealAxis) => {
                const config = parameterConfigs[axis.key];
                return (
                  <InputNumber
                    value={config.std}
                    min={0.000001}
                    disabled={config.distribution !== "NORMAL"}
                    style={{ width: 108 }}
                    onChange={(value) =>
                      handleParameter(axis.key, {
                        std: value == null ? null : Number(value),
                      })
                    }
                  />
                );
              },
            },
            {
              title: "MuJoCo",
              width: 190,
              dataIndex: "mujocoAdapter",
            },
            {
              title: "Isaac Lab",
              width: 220,
              dataIndex: "isaacLabAdapter",
            },
          ]}
        />

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
                description:
                  "MuJoCo ↔ Isaac paired evidence，识别 simulator-specific bias",
              },
              {
                title: "S3 真机只读 shadow",
                description:
                  "LOCKED：仅在独立 Level 0 安全审批后允许 joint/camera state 只读采集",
                status: "wait",
              },
              {
                title: "S4 受限真机运动",
                description:
                  "LOCKED：本分支不提供运动 dispatch；必须重新立项和现场验收",
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

      <Card
        title="5. Rerun trajectory/sensor 对齐与自动 Gap Report"
        size="small"
      >
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon
            title="MuJoCo run artifact 会自动生成 sim_trace.json。这里加载该文件和采用同一 schema 的只读真实 trace，后端将按 elapsed_s 最近邻对齐并输出门限化报告。Rerun .rrd 可由同一请求通过脚本生成。"
          />
          {traceError && <Alert type="error" showIcon title={traceError} />}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            <Card size="small" title="Simulation trace">
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) =>
                  void loadTrace(event.target.files?.[0], setSimulationTrace)
                }
              />
              <div style={{ marginTop: 8 }}>
                <Tag color={simulationTrace ? "success" : "default"}>
                  {simulationTrace ? "LOADED" : "WAITING"}
                </Tag>
              </div>
            </Card>
            <Card size="small" title="Read-only real trace">
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) =>
                  void loadTrace(event.target.files?.[0], setRealTrace)
                }
              />
              <div style={{ marginTop: 8 }}>
                <Tag color={realTrace ? "success" : "default"}>
                  {realTrace ? "LOADED" : "WAITING"}
                </Tag>
              </div>
            </Card>
          </div>
          <Space wrap>
            <Button
              type="primary"
              loading={generateGapReport.isPending}
              disabled={!simulationTrace || !realTrace}
              onClick={() => void handleGapReport()}
            >
              对齐并生成 Gap Report
            </Button>
            {generateGapReport.data && (
              <Button
                onClick={() =>
                  downloadText(
                    "sim_real_gap_report.md",
                    generateGapReport.data.markdown,
                    "text/markdown;charset=utf-8",
                  )
                }
              >
                下载 Markdown Report
              </Button>
            )}
            <Tag>Rerun timeline: elapsed_s</Tag>
            <Tag>frame: world</Tag>
          </Space>
          {generateGapReport.data && (
            <>
              <Descriptions bordered size="small" column={3}>
                <Descriptions.Item label="Gate">
                  <Tag
                    color={
                      generateGapReport.data.status === "PASS"
                        ? "success"
                        : generateGapReport.data.status === "FAIL"
                          ? "error"
                          : "warning"
                    }
                  >
                    {generateGapReport.data.status}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Aligned">
                  {generateGapReport.data.aligned_sample_count}/
                  {generateGapReport.data.real_sample_count}
                </Descriptions.Item>
                <Descriptions.Item label="Alignment ratio">
                  {(generateGapReport.data.alignment_ratio * 100).toFixed(1)}%
                </Descriptions.Item>
              </Descriptions>
              <Table
                size="small"
                pagination={false}
                rowKey="name"
                dataSource={generateGapReport.data.metrics}
                columns={[
                  { title: "Metric", dataIndex: "name" },
                  {
                    title: "Value",
                    render: (_, row) => `${row.value} ${row.unit}`,
                  },
                  {
                    title: "Threshold",
                    render: (_, row) =>
                      row.threshold == null
                        ? "—"
                        : `${row.threshold} ${row.unit}`,
                  },
                  {
                    title: "Status",
                    render: (_, row) => (
                      <Tag color={row.status === "PASS" ? "success" : "error"}>
                        {row.status}
                      </Tag>
                    ),
                  },
                ]}
              />
            </>
          )}
        </Space>
      </Card>

      <Card title="开源工具协同路线" size="small">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="MuJoCo">
            <Tag color="success">MjSpec 已接入</Tag>
            每次 run 先修改 mass / friction / joint damping / actuator gain /
            gravity，再编译独立 MjModel，并记录 spec hash。
          </Descriptions.Item>
          <Descriptions.Item label="Isaac Lab">
            <Tag color="success">Event plan 已生成</Tag>与 MuJoCo 使用同一
            parameter sample，映射为 EventTermCfg；Isaac runtime 不可用时只保留
            BLOCKED_BY_ENV，不伪造结果。
          </Descriptions.Item>
          <Descriptions.Item label="Rerun">
            <Tag color="success">Viewer pipeline 已接入</Tag>在 elapsed_s
            时间轴上对齐 TCP、关节、传感器延迟和深度摘要，可导出
            .rrd；不承担控制职责。
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
