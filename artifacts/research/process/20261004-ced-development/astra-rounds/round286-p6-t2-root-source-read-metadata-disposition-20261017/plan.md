# R286：弃用可选源码读取汇总

实际规划模型：gpt-6-astra。仅计划，STOP 等 ROOT 接受。

原 wrapper 四项 Promise rejection 的 reason 均仅保存为 `{}`；异常名称、消息和内部属性不可恢复。`TextEncoder` 不可用仅是假设。完整 wrapper 明确在汇总前保存了每项 invocation/actual。

物理原件独立核对显示：fb18d9、015b4e、d3785b、6000c9 四个 nested 读取均实际 exit0，输出无 Warning 前缀，分别450/450/477/454行。它们是成功读取回执；不能据此把失败的可选汇总标成成功，也不据输出字符串 SHA 冒充源码文件 pin。

处置仅 ABANDON 原 summary：零修复、零重放、零替代读取、零新增执行槽。ROOT 可逐项原样转显已保存的四 actual；不拼接显示缓存、不补造异常。原 R285 必要的物理源码 SHA/mode/边界、完整源码/native/input/argv 门继续适用。独立 Sol 源准备可继续，三运行槽仍由原门独立预留，未在本轮释放。

四个固定输入完整 SHA 见 plan.json/input-observation.json。产品、helper、测试、原脚本、角色、STATE/PHASE和预算不改；不增加 validator/collector、SQL/Git/审阅/运行。ROOT 接受弃用后继续原 R285 工作，本计划不证明行为或 T2 完成。

