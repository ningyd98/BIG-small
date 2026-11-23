/**
 * Build the editable thesis defense from the same local evidence as the manuscript.
 * Run with the bundled Node, RUNTIME_NODE_MODULES, RUNTIME_PYTHON and PRESENTATIONS_SKILL_DIR:
 *   node scripts/graduation/build_defense.mjs --work NEW_QA_DIRECTORY --output NEW_FILE.pptx
 * The private directory retains the source deck, validator receipt and page layouts.
 */
import { createHash } from "node:crypto";
import { constants as fsFlags } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: { work: { type: "string" }, output: { type: "string" } } });
if (!values.work || !values.output) throw new Error("Pass --work NEW_DIRECTORY and --output NEW_FILE.pptx");
const work = path.resolve(values.work);
const output = path.resolve(values.output);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const modules = process.env.RUNTIME_NODE_MODULES || path.resolve(path.dirname(process.execPath), "../node_modules");
const python = process.env.RUNTIME_PYTHON || path.resolve(path.dirname(modules), "../python/bin/python3");
const skill = process.env.PRESENTATIONS_SKILL_DIR;
if (!skill) throw new Error("PRESENTATIONS_SKILL_DIR must point to the installed Presentations skill");
process.env.RUNTIME_NODE_MODULES = modules;
const require = createRequire(path.join(path.dirname(modules), "package.json"));
const { Presentation, PresentationFile } = await import(pathToFileURL(require.resolve("@oai/artifact-tool")));
const { finalizePresentation } = await import(pathToFileURL(path.join(skill, "container_tools/artifact_tool_utils.mjs")));
const rounds = "artifacts/research/process/20261004-ced-development/astra-rounds";
const current = rounds + "/round-graduation-integration-20261123";
const dynamic = rounds + "/round-graduation-dynamic-qualification-20261123";
const sources = {
  calibration: current + "/perception.public.json",
  allocation: current + "/allocation.public.json",
  decisions: current + "/decisions.public.json",
  installation: current + "/installation.public.json",
  teacher: rounds + "/round-v10-phase6-20261122/validation.public.json",
  lift: rounds + "/round-v10-phase7-20261123/vision.public.json",
  components: rounds + "/round-p1-hard-limit-prefix-resume-20261120/final-batch-summary.json",
  physics: dynamic + "/physics.public.json",
  guarded: dynamic + "/vision.public.json",
  guarded2: rounds + "/round-graduation-guarded-clock-20261123/vision.public.json",
  markerLoss: rounds + "/round-graduation-guarded-clock-20261123/marker-loss.public.json",
  playback: rounds + "/round-graduation-pickplace-playback-20261123/playback.public.json",
};
const data = Object.fromEntries(await Promise.all(Object.entries(sources).map(async ([key, file]) =>
  [key, JSON.parse(await fs.readFile(path.join(root, file), "utf8"))])));
const { calibration, decisions, installation, teacher, lift, components, physics, guarded, guarded2, markerLoss, playback } = data;
const figure = calibration.calibration_views_figure;
const image = await fs.readFile(path.join(root, current, figure.filename));
if (createHash("sha256").update(image).digest("hex") !== figure.sha256 ||
    figure.panels.length !== 3 || figure.panels.some(panel => panel.status !== "CAPTURED")) {
  throw new Error("The three captured source panels or their bound image digest are unavailable");
}
await fs.mkdir(work, { recursive: false });
await fs.mkdir(path.join(work, "validated"));
const draft = path.join(work, "draft.pptx");
const privateFinal = path.join(work, "validated", "deck.pptx");
const receipt = path.join(work, "quality-receipt.json");
const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const font = "Noto Sans CJK SC";
const color = { ink: "#172D35", mid: "#425B63", teal: "#087460", paper: "#FFFFFF",
  pale: "#EDF5F2", dark: "#153B3A", mint: "#86D7AE", soft: "#C7E0D9" };
const noLine = { fill: "none", width: 0 };

function txt(slide, name, value, x, y, width, height, size, options = {}) {
  const shape = slide.shapes.add({ name, geometry: "textbox",
    position: { left: x, top: y, width, height }, fill: "none", line: noLine });
  shape.text = value;
  shape.text.style = { typeface: font, fontSize: size, bold: options.bold || false,
    color: options.color || color.ink, alignment: options.align || "left",
    verticalAlignment: "middle", autoFit: "none", wrap: "none", insets: 0 };
  return shape;
}

function page(title, notes, references, dark = false) {
  const slide = deck.slides.add();
  slide.background.fill = dark ? color.dark : color.paper;
  if (title) txt(slide, "页标题", title, 72, 55, 1140, 77, 52,
    { bold: true, color: dark ? color.paper : color.ink });
  slide.speakerNotes.text = notes + "\n\n本地来源\n" + references.map(name => sources[name] || name).join("\n");
  return slide;
}

function table(slide, values, widths, y, rowHeight) {
  const total = widths.reduce((sum, width) => sum + width, 0);
  const object = slide.tables.add({ rows: values.length, columns: widths.length, left: 72,
    top: y, width: total, height: rowHeight * values.length, columnWidths: widths, values });
  object.styleOptions = { headerRow: false, bandedRows: false, firstColumn: false };
  object.borders.assign({ fill: color.paper, style: "solid", width: 2 });
  for (const [row, valuesRow] of values.entries()) {
    object.rows[row].height = rowHeight;
    for (const [column] of valuesRow.entries()) {
      const cell = object.getCell(row, column);
      cell.fill = row === 0 ? color.dark : row % 2 ? color.pale : "#F6F9F8";
      cell.text.style = { typeface: font, fontSize: row === 0 ? 23 : 27, bold: row === 0 || column === 0,
        alignment: "left", verticalAlignment: "middle", color: row === 0 ? color.paper : color.ink };
      object.cells.block({ row, column, rowCount: 1, columnCount: 1 }).assign({
        margins: { top: 7, left: 17, right: 10, bottom: 7 }, anchor: "center",
      });
    }
  }
  return object;
}

const numbers = new Intl.NumberFormat("en-US");
const frac = (a, b) => a + "/" + b;
const names = { axial: "登记顶视", left: "偏视 A", right: "偏视 B" };
const teacherGroup = teacher.registered_readback;
const gated = teacher.collection;
const liftFacts = lift.lift.physical_facts;
const historical = components.development_fresh;
{
  const slide = page("", "课题面向桌面机械臂的抓取、移送、释放任务。图中三个相机画面来自本轮 MuJoCo 开发采集。物体摆放和初始高度相同，各机位独立复位。", [
    "docs/开题报告_集成电路工程_20261024.md", "allocation", "calibration", current + "/" + figure.filename]);
  txt(slide, "专业", "集成电路工程 · 毕业设计", 72, 42, 850, 42, 25, { color: color.teal, bold: true });
  txt(slide, "论文题名", "面向边缘智能场景的小型机械臂\n云边协同控制系统的设计", 72, 101, 1140, 164, 59, { bold: true });
  const position = { left: 72, top: 279, width: 1136, height: 337.1 };
  slide.images.add({ blob: image.buffer.slice(image.byteOffset, image.byteOffset + image.byteLength),
    contentType: "image/png", alt: "同一开发摆放在物理步零的三个真实仿真相机画面", fit: "contain", position });
  txt(slide, "署名", "宁业栋    ·    2026 年 11 月 23 日", 72, 639, 1136, 42, 24, { color: color.mid });
}
{
  const slide = page("桌面抓放的云、边、端分工",
    "云端只返回候选技能。边缘对当前版本、目标、相机证据和时效作判断，端侧在控制循环内执行受限技能。风险、费用和修复的软件对照使用固定夹具。端侧 RGB-D 几何估计与离线物理真值分属不同路径。", [
      "docs/thesis/graduation-20261123/manuscript.md", "docs/开题报告_集成电路工程_20261024.md",
      "docs/harness.md", "teacher"]);
  txt(slide, "动作情境", "任务指令进入系统后，每个候选动作都绑定计划版本和当前观测。", 72, 145, 1136, 52, 29, { color: color.mid });
  const lanes = [
    [72, "云端", "gpt-6.1-sol", "将指令转换成\n白名单技能与目标。"],
    [485, "边缘", "风险与成本规则", "检查证据是否过期，\n选择继续、复测或请求云端。"],
    [900, "端侧", "OpenCV 与控制器", "由 RGB-D 估计位姿，\n通过安全检查后执行。"],
  ];
  for (const [x, label, component, detail] of lanes) {
    txt(slide, label, label, x, 226, 295, 75, 51, { bold: true, color: color.teal });
    txt(slide, label + "组件", component, x, 317, 305, 50, 30, { bold: true });
    txt(slide, label + "职责", detail, x, 383, x > 800 ? 310 : 380, 99, 26);
  }
  txt(slide, "云到边", "→", 365, 238, 75, 60, 43, { color: color.teal, align: "center" });
  txt(slide, "边到端", "→", 784, 238, 75, 60, 43, { color: color.teal, align: "center" });
  txt(slide, "动作反馈", "动作后回读新观测。抬升或放置缺少可验证条件时，执行器停止。", 72, 555, 1136, 78, 29,
    { bold: true, color: color.ink });
}
{
  const slide = page("留出摆放的定位覆盖与误差",
    "开发分组以摆放为单位，三个探索摆放和三个留出摆放分开。三种相机视角、三种初始高度分别独立复位，每格在预定的六个物理步采样。P90 为有效 RGB-D 顶心估计与独立物理顶心之间三维欧氏距离的第 90 百分位。无解码帧仍计入覆盖分母。正式 G1 还要求独立静态抓放成功率至少 90%。", [
      "allocation", "calibration", "components"]);
  const rows = calibration.holdout_by_view;
  if (rows.length !== 3 || new Set(rows.map(r => r.view)).size !== 3 ||
      rows.some(r => !Object.hasOwn(names, r.view))) throw new Error("Unexpected holdout views");
  const cells = calibration.capture;
  const pooled = calibration.by_split_and_mode.find(r => r.split === "holdout" && r.mode === calibration.primary_mode);
  txt(slide, "开发标定规模", `6 个独立摆放，${cells.cells} 个工况，采得 ${frac(cells.captured, cells.allocated)} 帧。`, 72, 147, 1136, 60, 30,
    { color: color.mid });
  table(slide, [
    ["留出组 · 3 个独立摆放", "顶心有效观测", "覆盖率", "三维误差 P90"],
    ...rows.map(row => [names[row.view], frac(row.observed, row.allocated),
      (100 * row.observed / row.allocated).toFixed(1) + "%",
      row.top_center_p90_mm === null ? "无有效值" : row.top_center_p90_mm.toFixed(1) + " mm"]),
  ], [331, 265, 204, 336], 237, 70);
  txt(slide, "指标解释", `合计 ${frac(pooled.observed, pooled.allocated)} 帧有效，条件 P90 为 ${(pooled.errors.object_top_center_3d_m.p90 * 1000).toFixed(2)} mm。独立留出摆放为 3 个。`,
    72, 542, 1136, 55, 27, { bold: true });
  txt(slide, "闭环指标", `另一次闭环开发试验中，${frac(historical.physical_success.successes, historical.assigned)} 个新位姿实现独立物理抓放成功。`,
    72, 606, 1136, 49, 24, { color: color.mid });
}
{
  const slide = page("固定目标抓放与视觉接入",
    "左侧以预设 TCP 执行完整抓放并用独立物理序列复算，两段驻留窗均含起止步。五项保护负控覆盖无接触、不可达、超时保持、急停、空手放置。右侧使用另一实例的真实相机图像。五帧取自复位和静置后的两个物理步；同一步重新取帧时，目标求解入口因新鲜度未满足而拒绝，未进入 PRE 或运动反馈。两条开发记录均未占用正式运行名额。", [
      "physics", "guarded", dynamic + "/allocation.public.json"]);
  const liftWindow = physics.windows.lift;
  const releaseWindow = physics.windows.release;
  const negatives = Object.entries(physics.cases).filter(([name]) => name !== "positive_pick_place");
  const top = guarded.whole.top_center;
  if (!physics.independent_outcome.success || !physics.original_positive_passed ||
      !liftWindow.entire_registered_duration_met || !releaseWindow.entire_registered_duration_met ||
      guarded.stop.phase !== "GROUNDING" || !guarded.stop.reason.includes("capture_not_new_and_monotonic") ||
      !guarded.safe_stop.success || guarded.controller_dispatches !== 0 || guarded.feedback_only.top_center.frames !== 0) {
    throw new Error("The two development observations changed; review their interpretation");
  }
  txt(slide, "固定目标", "预设 TCP 的抓放", 72, 167, 520, 63, 36, { bold: true });
  txt(slide, "守卫开发", "首个仿真视觉实例", 678, 167, 530, 63, 36, { bold: true });
  txt(slide, "抬升达标样本", frac(liftWindow.passed_samples, liftWindow.samples), 72, 246, 535, 107, 76,
    { color: color.teal, bold: true });
  txt(slide, "派发次数", guarded.controller_dispatches + " 次", 678, 246, 530, 107, 76,
    { color: color.teal, bold: true });
  txt(slide, "抬升窗", "抬升窗达标样本 · " + liftWindow.duration_s.toFixed(2) + " s", 75, 350, 537, 58, 30, { bold: true });
  txt(slide, "停止步", "控制器派发 · 第 " + guarded.stop.physics_step + " 步停止", 681, 350, 525, 58, 30, { bold: true });
  txt(slide, "逐步结果",
    "放置窗 " + frac(releaseWindow.passed_samples, releaseWindow.samples) + " 个样本达标，持续 " + releaseWindow.duration_s.toFixed(2) + " s。\n" +
    "独立物理复算抬升 " + (physics.independent_outcome.measured_lift_m * 1000).toFixed(1) + " mm。\n" +
    frac(negatives.filter(([, row]) => row.passed).length, negatives.length) + " 个保护负控得到预期结果。", 75, 428, 565, 128, 25);
  txt(slide, "真实像素与守卫",
    frac(top.estimated, top.frames) + " 帧估计出顶心，来自 " + guarded.whole.distinct_sample_steps + " 个物理步。\n" +
    "同一步获取的新图未满足时序要求，\n首个动作在目标求解阶段被拒绝。", 681, 428, 529, 128, 25);
  txt(slide, "开发界限", "首个视觉实例在控制器启动前安全停止，留下了同一物理步重拍时的时序记录。", 72, 600, 1140, 62, 25,
    { color: color.mid });
}
{
  const stage = guarded2.stages[0];
  const feedback = guarded2.feedback_only.top_center;
  const feedbackShield = guarded2.research_shield.FEEDBACK;
  const pre = stage.pre.conditions;
  const accepted = pre.filter(c => c.status === "PASS").length;
  const absent = guarded2.stages.filter(s => s.status === "NOT_RUN").length;
  const runSteps = stage.controller_return_step - stage.dispatch_step;
  const [lastSeen, rejected, terminal] = markerLoss.frames;
  if (guarded2.id === guarded.id || stage.skill !== "MOVE_ABOVE" || !stage.pre.shield.allowed ||
      accepted !== pre.length || !stage.dispatched || !guarded2.safe_stop.success || guarded2.completed_posts !== 0 ||
      stage.controller_result.details.details.reason !== "servo registered marker geometry unavailable" ||
      !lastSeen.detectors.SUBPIX.observed_ids.includes(7) || rejected.step !== terminal.step ||
      [rejected, terminal].some(f => f.detectors.SUBPIX.observed_ids.includes(7))) {
    throw new Error("The independent guarded run no longer supports the recorded outcome");
  }
  const slide = page("第二个视觉实例进入运动反馈",
    `独立登记的新开发实例在同一步复用已经验证的交接图，向求解、三项前置条件和安全盾提供相同的证据。首步 MOVE_ABOVE 的 PRE 获准，控制器收到 ${guarded2.accepted_joint_target_commands} 条关节目标和一次保持。首个动作的运动跨度为 ${runSteps} 物理步。${feedback.frames} 张反馈帧按 30 Hz 采样，${frac(feedback.estimated, feedback.frames)} 帧可估计顶心，条件 P90 为 ${(feedback.p90_m * 1000).toFixed(3)} mm，最大为 ${(feedback.max_m * 1000).toFixed(3)} mm。第 ${lastSeen.step} 步仍能识别编号 7 的标记，第 ${rejected.step} 步的反馈帧和终止帧均未识别该标记。视觉伺服报告 VISUAL_SERVO_REJECTED 后停止。遮挡物身份与单一成因仍待验证。本例也未取得通用连续运动界。`, ["guarded2", "markerLoss", "guarded"]);
  txt(slide, "新实例", `r593 仿真相机共采集 ${guarded2.explicit_frames} 帧。首个动作以同一交接观测通过求解与准入。`,
    72, 148, 1140, 58, 28, { color: color.mid });
  table(slide, [
    ["MOVE_ABOVE", "实际记录", "反馈与控制"],
    ["动作前", frac(accepted, pre.length) + " 项前置条件通过", "安全盾允许启动控制器"],
    ["运动中", guarded2.accepted_joint_target_commands + " 条关节目标", frac(feedbackShield.allowed, feedbackShield.calls) + " 次反馈安全检查允许"],
    ["停止时", "第 " + stage.controller_return_step + " 个物理步", "相机无法重建登记标记几何"],
  ], [275, 370, 491], 229, 66);
  txt(slide, "动作跨度", `从第 ${stage.dispatch_step} 步到第 ${stage.controller_return_step} 步，实际运动 ${runSteps} 步。反馈顶心有效 ${frac(feedback.estimated, feedback.frames)} 帧。`,
    72, 521, 1140, 61, 29, { bold: true });
  txt(slide, "未到达", `首个动作未进入后置检查，其余 ${absent} 个技能未运行。`, 72, 603, 1140, 49, 25, { color: color.mid });
}
{
  const slide = page("首组教师在抬升后停止", "这是一次正式教师资格尝试，使用登记首组的唯一名额。安全盾在 LIFT POST 给出 ALLOW，物体升高和稳定两个后置条件仍为 UNKNOWN。在线观测缺少误差上界与采样间运动界。离线物理采样用于解释结果，不能回填在线门控。", ["teacher", "lift"], true);
  const candidates = Object.values(Object.fromEntries(teacherGroup.group_scores));
  const expected = candidates.length;
  const passed = candidates.filter(x => x !== null).length;
  if (passed !== 0 || liftFacts.object_lifted !== "UNKNOWN" || liftFacts.object_stable !== "UNKNOWN") {
    throw new Error("Frozen teacher outcomes changed");
  }
  txt(slide, "资格分母", frac(passed, expected), 72, 173, 400, 158, 119, { bold: true, color: color.mint });
  txt(slide, "资格状态", "组取得教师资格", 79, 335, 405, 56, 32, { bold: true, color: color.paper });
  txt(slide, "组状态", `首组已运行，另 ${teacherGroup.not_run_groups.length} 组未运行。\n首组资格仍为 UNKNOWN。`, 79, 407, 402, 98, 26, { color: color.soft });
  txt(slide, "记录规模", `${gated.controller_returned} 个返回动作，${gated.admission_rows} 次准入检查\n${numbers.format(gated.allocated_frames)} 帧，${numbers.format(gated.physics_steps)} 个物理步`,
    550, 193, 648, 106, 32, { bold: true, color: color.paper });
  const a = lift.lift.nominal_endpoint_center_height_change_m;
  const sample = teacher.lift_diagnosis.offline_physics_samples.object_center_height_delta_m;
  txt(slide, "高度估计", `标记估计名义升高 ${(a.SUBPIX*1000).toFixed(1)}–${(a.NONE*1000).toFixed(1)} mm。\n离线物理样本相差 ${(sample*1000).toFixed(3)} mm。`,
    550, 339, 657, 94, 26, { color: color.soft });
  txt(slide, "停止原因", "测量误差上界和采样间运动界均缺失，\n持续抬升与稳定的后置条件未获确认。",
    550, 477, 650, 108, 28, { color: color.paper, bold: true });
}
{
  const slide = page("云端请求随风险与通信成本变化",
    "数值输入来自 SOFTWARE_ONLY 夹具。固定失败概率下，只改动账本的网络时间，软件策略发生切换。风险回放另有32条预分数值样本，由8条训练、18条校准、4条选择、2条留出构成。缩至8个校准组或给选择资料加入域外样本均得不到可行候选。费用没有账单依据。", ["decisions"]);
  const cases = ["low_transfer_cost", "high_transfer_cost"].map(
    id => decisions.policy.find(row => row.case === id));
  const labels = { CONTINUE: "本地继续", REQUEST_CLOUD: "请求云端" };
  txt(slide, "对照条件", "同一软件场景，继续动作的失败概率固定为 0.09，请求云端为 0.01。", 72, 146, 1136, 58, 28, { color: color.mid });
  table(slide, [
    ["夹具中的累计网络时间", "规则选择", "新增模型调用"],
    ...cases.map(c => [c.fixture_ledger.network_s.toFixed(1) + " s", labels[c.action], String(c.model_request_delta)]),
  ], [470, 365, 301], 236, 74);
  txt(slide, "成本账本", `账本保留 ${decisions.cost.ledger.summary.model_requests} 个逻辑已发请求，${decisions.cost.ledger.summary.application_bytes} 字节应用载荷。`,
    72, 505, 1136, 66, 33, { bold: true, color: color.teal });
  txt(slide, "代价范围", "成功与已发超时计入。未发取消和原样重报不增加次数。费用未知。",
    72, 599, 1136, 55, 24, { color: color.mid });
}
{
  const slide = page("释放完成后的局部修复",
    "三个步骤构成同一图，释放已完成，验证受目标图像失效影响，遥测不依赖目标图像。两个方法都保留释放的已完成效果，采用同一观测与相同故障。软件暂存与恢复回执来自 mock 网关，SQLite 使用真实持久化。两条路径均无物理开始回执。", ["decisions"]);
  txt(slide, "故障", "释放已完成。目标图像失效后，结果验证需要重做，遥测仍可沿用。", 72, 149, 1136, 55, 28, { color: color.mid });
  const local = decisions.repair.paired.find(v => v.method === "local");
  const full = decisions.repair.paired.find(v => v.method === "full_remaining");
  const repairRows = [["局部修复", local], ["完整剩余重规划", full]];
  table(slide, [
    ["同一故障和依赖图", "改写待执行步骤", "再次排入释放", "重启后的网关调用"],
    ...repairRows.map(([label, v]) => [label, frac(v.actual_replaced_ids.length, v.new_candidate_steps.length),
      String(v.completed_nonrepeatable_in_pending), String(v.restart_gateway_calls.length)]),
  ], [320, 266, 234, 316], 239, 71);
  const end = decisions.retry_budget.map(v => v.remaining).join("、");
  txt(slide, "预算", `重启后逐次读取预算，余额依次为 ${end}。`, 72, 493, 1136, 68, 30, { bold: true, color: color.teal });
  txt(slide, "幂等保护", "重复故障不再扣额。计划升至版本 2 后，旧版请求被拒绝。", 72, 588, 1136, 57, 26, { color: color.mid });
}
{
  const mediaFile = path.join(root, "artifacts/thesis_report/graduation-20261123", playback.filename);
  if (playback.filename !== "抓放开发实例回放.gif" || playback.trial !== "development-01" ||
      playback.camera_frames + playback.gap_cards !== playback.output_frames || playback.gap_cards !== 2 ||
      createHash("sha256").update(await fs.readFile(mediaFile)).digest("hex") !== playback.decoded_sha256) {
    throw new Error("Archived playback or bound source manifest changed");
  }
  const slide = page("工程交付与离线演示",
    `放映时点击左栏文件名，或在答辩幻灯同一目录打开该 GIF。播放时长 ${(playback.total_display_ms / 1000).toFixed(2)} 秒，展示历史 development-01 的九个动作。采样间隔卡标明抓取和释放过程中缺少原相机帧，两种退避依实际执行次序呈现。该次展示来自已有的二十个位姿，独立物理成功五例。回放使用归档原帧，重新制作动图没有执行机械臂动作。在项目根目录运行末页命令可复算验收矩阵；有 episode 时可增加 --episode 和已安装 CLI 的 --cli 路径。正式结束条件仍需独立误差界、连续运动界和教师资格。`, [
      "playback", "installation", "scripts/graduation/demo.py", "scripts/graduation/decision_replay.py", "calibration", "teacher"]);
  txt(slide, "播放位置", "播放同目录的归档演示", 72, 163, 580, 61, 33, { bold: true, color: color.teal });
  const mediaLink = txt(slide, "本地播放文件", playback.filename, 72, 230, 585, 64, 42, { bold: true });
  mediaLink.hyperlink = { uri: encodeURI(playback.filename), isExternal: true };
  txt(slide, "实例来源",
    `历史位姿 01，全批独立物理成功 ${frac(playback.batch.independent_physical_success, playback.batch.assigned)}。\n` +
    `${playback.camera_frames} 张仿真相机原帧，播放 ${(playback.total_display_ms / 1000).toFixed(2)} 秒。\n` +
    `抓取与释放各有一张缺帧间隔卡。`, 72, 311, 595, 135, 25);
  txt(slide, "安装验收", "离线软件交付", 697, 163, 511, 61, 33, { bold: true, color: color.teal });
  txt(slide, "离线记录", `Python ${installation.python} 独立环境离线安装。\nprepare 阶段输出 ${installation.evidence_files} 份证据文件。\n重复目录与被篡改的副本均被拒绝。`,
    697, 246, 510, 179, 26);
  txt(slide, "命令", "python -m scripts.graduation.demo", 72, 487, 1136, 74, 39, { bold: true });
  txt(slide, "演示边界", "在项目根目录复算证据矩阵。正式研究仍需取得测量误差界、采样间运动界和教师资格。", 72, 591, 1136, 57, 24, { color: color.mid });
}

for (const [index, slide] of deck.slides.items.entries()) {
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(work, `slide-${index + 1}.layout.json`), await layout.text());
}
await (await PresentationFile.exportPptx(deck)).save(draft);
const inspectors = path.join(skill, "container_tools");
const tableSlides = [3, 5, 7, 8];
await finalizePresentation({
  workspaceDir: work, candidatePath: draft, finalPath: privateFinal, receiptPath: receipt,
  pythonExecutable: python, explicitTotalSlideCount: 9, requiredNativeTableOwnerSlides: tableSlides,
  integrityValidatorPath: path.join(inspectors, "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(inspectors, "inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry",
    "--validate-heading-fit", ...tableSlides.flatMap(n => ["--require-native-table-slide", String(n)])],
  fontPolicy: { basis: "design", families: [font] }, verifyArtifactToolImport: true,
});
await fs.mkdir(path.dirname(output), { recursive: true });
await fs.copyFile(privateFinal, output, fsFlags.COPYFILE_EXCL);
console.log(JSON.stringify({ slides: deck.slides.items.length, output, receipt,
  sha256: createHash("sha256").update(await fs.readFile(output)).digest("hex") }));
