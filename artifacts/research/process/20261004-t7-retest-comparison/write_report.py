"""Render the audited comparison into the repository's existing evidence format."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).parent


def read(name):
    return json.loads((BASE / name).read_text())


def value(number, digits=2):
    return "N/A" if number is None else f"{number:.{digits}f}"


def rate(item):
    lo, hi = item["wilson_95"]
    return (
        f"{item['count']}/{item['denominator']}（{100 * item['rate']:.1f}%；"
        f"95% CI {100 * lo:.1f}–{100 * hi:.1f}%）"
    )


if __name__ == "__main__":
    data = read("comparison-summary.json")
    validation = read("independent-validation.json")
    retest = read("retest-validation.json")
    protocol = read("independent-60/protocol.json")
    if not validation["valid"] or not retest["valid"]:
        raise ValueError("report requires both independent audits")
    a, b = (data["methods"][key] for key in ("qwen3vl", "qwen35"))
    table = [
        ("目标缺失时误操作率 ↓", rate(a["absent_misoperation"]), rate(b["absent_misoperation"])),
        ("定位误差 P90（mm）↓", value(a["localization_p90_mm"]), value(b["localization_p90_mm"])),
        ("定位 P90 有效覆盖率", rate(a["localization_coverage"]), rate(b["localization_coverage"])),
        ("目标存在任务成功率 ↑", rate(a["normal_task_success"]), rate(b["normal_task_success"])),
        (
            "全部分配任务成功率 ↑",
            rate(a["all_assigned_task_success"]),
            rate(b["all_assigned_task_success"]),
        ),
        (
            "端到端墙钟延迟 P95（s）↓",
            value(a["wall_latency_p95_s"]),
            value(b["wall_latency_p95_s"]),
        ),
        (
            "每任务模型调用总延迟 P95（s）↓",
            value(a["model_latency_p95_s"]),
            value(b["model_latency_p95_s"]),
        ),
        (
            "目标存在失败惩罚耗时 P95（s）↓",
            value(a["failure_penalized_normal_latency_p95_s"]),
            value(b["failure_penalized_normal_latency_p95_s"]),
        ),
        ("API 账单费用（元/任务）", "0", "0"),
        ("含电费、折旧的总费用（元/任务）", "未测", "未测"),
        (
            "实际推理请求（总数；每任务）",
            f"{a['chat_requests']}；{a['chat_requests_per_task']:.2f}",
            f"{b['chat_requests']}；{b['chat_requests_per_task']:.2f}",
        ),
        ("误完成（全部 60）", str(a["false_completions"]), str(b["false_completions"])),
        (
            "环境阻塞 / 物理安全违规",
            f"{a['blocked']} / {a['safety_violations']}",
            f"{b['blocked']} / {b['safety_violations']}",
        ),
    ]
    lines = [
        "# T7 典型失败复测与独立模型比较",
        "",
        "日期：2026-10-04（Asia/Shanghai）。",
        "",
        "**结论：历史失败稳定复现；两个候选均未通过 G1 任务可靠性门槛。** "
        "本次是预先冻结的独立探索性比较，不是正式 G1 验收，也不将 T8 标为完成。",
        "",
        "## 典型失败复测",
        "",
        "原样复跑 smoke v2 全部 20 例：2 成功、18 失败、0 环境阻塞。"
        "逐例状态、终止原因、动作数、模型调用数均与历史一致。"
        "4 个目标缺失场景全部执行 1–4 个任务物理技能，误操作率为 4/4；误完成为 0/20。"
        "这两项统计含义不同。",
        "",
        "失败分布：目标证据失效 6、抬升保持未验证 3、抬升效果未验证 2、抓取前置条件不足 2、"
        "释放前置条件不足 1、无效深度导致规划拒绝 2、安全停止 2。",
        "",
        f"[独立复算](retest-validation.json) valid=true、accepted=true、errors=[]；"
        f"复算 {retest['physical_samples']:,} 个物理样本、{retest['frames']} 帧、"
        f"{retest['actions']} 个动作。物理样本数可能随停止时刻变化，不据此改动成功门槛。",
        "",
        "## 独立测试比较",
        "",
        "60 个新场景：40 个目标存在、20 个目标缺失，每场景两个模型各执行一次。"
        "全部 120 例保留；使用相同场景、相同初始 RGB/depth、同一控制器、安全门禁和验证预算。"
        "场景顺序预先随机，两模型先后顺序交替。两者都使用 Q4_K_M、320×240、normalized_1000、"
        "temperature=0、num_ctx=8192、num_predict=512、think=false；仅模型身份不同。",
        "",
        "| 指标 | Qwen3-VL 4B（当前 T7） | Qwen3.5 4B |",
        "| --- | ---: | ---: |",
        *[f"| {label} | {left} | {right} |" for label, left, right in table],
        "",
        "定位只取每场景首个回复中正确实例命中且深度有效的三维表面点，"
        "与离线独立标注的已落稳方块顶部几何中心计算欧氏距离；"
        "不是 TCP 误差、像素误差或可见表面质心误差。"
        "拒答和错误定位不补造误差，但仍保留在覆盖率和任务成功率分母中。"
        "覆盖率不同的两个条件 P90 不能直接解释为全面定位能力优劣。",
        "",
        "目标缺失误操作按至少执行一个实际物理任务技能计数，安全停止不计为误操作。"
        "紫色不在本场景注册颜色 red/blue/yellow 中；该结果仅覆盖这类缺失请求。"
        "成功要求在线完成、独立物理成功、指令目标存在三者同时成立；"
        "正常层 40 是主要成功率分母，全分配 60 另外报告，安全拒绝不计为抓放成功。",
        "",
        "端到端延迟从首次采集到终态评价与证据落盘，计入模型调用、物理执行和失败；"
        "不含仿真初始化和两次单 token 文本预热。模型延迟包含实际加载时间和每任务所有重观测调用。"
        "RTX 4070 Ti SUPER 共用同一 Ollama 服务，切换可能造成加载；先后顺序各平衡 30 次，"
        "本次结果不等同于模型长期单独驻留时的热延迟，也未测 TTFT。"
        "目标存在失败任务按预注册 120 秒计入惩罚耗时，因此不能将提前失败的低延迟称为可靠改善。",
        "",
        "两者仅访问 localhost Ollama，实际 API 账单为 0；用户确认没有机器计费单价。"
        "未测整机能耗、电价与折旧，不能把 0 元 API 费用写成总费用。"
        "[逐任务请求记录](independent-60/cases/)含 provider 实报 token、加载和生成时长；"
        "不使用估计 token 冒充实际消耗。",
        "",
        "## 风险与统计限制",
        "",
        f"独立测试的 Qwen3-VL 误完成为 {a['false_completions']}/60，"
        f"Qwen3.5 为 {b['false_completions']}/60。"
        "指令要求不存在的紫块时，抓放其他颜色方块即使被在线与物理层判成功，也被任务评分判失败。"
        "语义评分发生在终态，当前门禁不能保证执行前阻止这类误操作。",
        "",
        f"目标缺失首个响应的 null target / 低置信分别为 Qwen3-VL "
        f"{a['absent_first_response_null_target']}/20、{a['absent_first_response_low_confidence']}/20；"
        f"Qwen3.5 {b['absent_first_response_null_target']}/20、"
        f"{b['absent_first_response_low_confidence']}/20。"
        "零动作不自动代表模型明确识别目标缺失，几何或技能合同拒绝也能产生零动作。",
        "",
        "比例报告 Wilson 双侧 95% 区间；0/n 不代表风险为零。连续指标和差值按场景、按正常/缺失分层"
        "配对 bootstrap 10000 次，保留两个模型同一场景的配对关系；见"
        "[完整统计](comparison-summary.json)。这是探索性结果，无正式多重校正假设检验或收益验收。"
        "两个方法的正常任务成功率均远低于 G1 90% 门槛，不声称费用节省或可靠性能胜出。",
        "",
        "## 来源与验证",
        "",
        f"预注册核对 {protocol['historical_scene_records']} 条历史场景记录，"
        "种子与精确几何重叠均为 0；不依靠含种子的场景哈希单独证明不重复。"
        f"另核对 {validation['historical_unique_rgb_sha256']:,} 个历史 RGB 哈希，"
        "初始 RGB 重叠为 0。"
        "此检查不保证任意语义近重复的完备排除；测试仍限原开发分布的直立有色方块。",
        "",
        f"[独立验证](independent-validation.json) valid=true、errors=[]；120/120 记录完整，"
        f"配对初始像素一致，重放 {validation['physical_samples']:,} 个连续物理样本、"
        f"{validation['frames']} 帧、{validation['actions']} 个动作。"
        "核对物理结果、语义成功合取、误操作计数、定位参考、模型调用数、"
        "帧/源码哈希及 STOP 后无新动作。",
        "",
        f"协议 SHA-256：`{data['protocol_sha256']}`。"
        "[协议](independent-60/protocol.json)、[分配清单](independent-60/assignments.json)、"
        "[模型配置](independent-60/models.json)、[环境](environment.json)均保留。"
        "运行脚本与生产源码按冻结 SHA 复核，未更改模型、控制器、阈值或历史数据。",
        "",
        "离线统计脚本通过 6 项手算与分母反例检查及 Ruff；本轮使用真实复跑和逐步证据重放验证，"
        "不声称重跑整个仓库测试套件。",
        "",
        "复算命令（仓库根目录）：",
        "",
        "```bash",
        ".venv/bin/python artifacts/research/process/20261004-t7-retest-comparison/analyze.py",
        ".venv/bin/python artifacts/research/process/20261004-t7-retest-comparison/write_report.py",
        "```",
        "",
        "重新执行必须将 compare.py 与 analyze.py 放在新的 `artifacts/research/process/<new-name>/` "
        "目录，再依次运行 compare.py preregister、compare.py run 和 analyze.py。"
        "现有分配与模型输入均不能覆盖；该运行器明确拒绝隐式重试或续跑。",
        "",
    ]
    (BASE / "acceptance.md").write_text("\n".join(lines), encoding="utf-8")
    print(BASE / "acceptance.md")
