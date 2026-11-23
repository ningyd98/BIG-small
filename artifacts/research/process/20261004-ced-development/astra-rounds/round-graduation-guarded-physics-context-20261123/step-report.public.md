# 动作相对物理步的研究 Shield 验证

首次无派发夹具以独立开发租约和实时 RGB-D 完成三项注册 PRE。开发接口没有为 PHYSICS_STEPS 契约传入动作相对步号，原 Shield 的 STEP_TIMEOUT 规则因此返回 PHYSICS_STEP_INVALID。原失败索引 SHA256 为 fb7142528f3c4c3c249d69e980479d07938c461e3092ad32a45bf9002924cc63。发生问题时 r2 身份尚未签发。

每步 PRE 在同一绑定、任务、契约、技能、episode 和原观察上固定绝对起点。开发接口在派发前复核起点与帧有效期，传给研究 Shield 的计数为当前真实步号减去该动作起点。首个反馈可处于相对步 0，后续反馈随真实物理步推进。控制回执按真实返回步、原技能窗口和内层 ActionResult.details 核验。需要额外停留时，开发接口在推进前核对原窗口剩余步数。

软件验证覆盖了两段不同的绝对起点、原点归零、反馈及 POST 逆序、错误任务和来源、错误时间类型、坏 horizon 以及端点和端点加一。原窗口函数分别核对了 LIFT 的 1920 步动作限额与 2040 步总终点，以及 RELEASE 的 240 步返回限额与 480 步总终点。零派发夹具在绝对 120 / 相对 0 得到三项原 PRE 的 PASS、研究 Shield 整体 ALLOW 和 STEP_TIME_OK。开发回执序列化与布尔负控的后续修复见专项报告。

独立实测保留同一个 r2 身份。原始计数和像素来源逐项匹配了 92 次 Shield 上下文，包括首次 PRE 和 91 次运动反馈。反馈相对步为 0、8、16，直至 720。第 848 个绝对步的第 92 帧反馈在视觉测量层停止，控制器返回时动作经历 728 步。真实独立回执确认其位于 MOVE_ABOVE 的原始 1920 步窗口内。控制器错误为 VISUAL_SERVO_REJECTED。LIFT、RELEASE、后续 POST 及原生完整时域没有实测资格。

[本轮验证](verification.public.json) · [开发预检修复](../round-graduation-guarded-preflight-repair-20261123/step-report.public.md) · [真实开发运行](../round-graduation-guarded-clock-20261123/step-report.public.md)
