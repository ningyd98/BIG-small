# R305：G1 元数据 SQL seam 选择器范围修正

实际模型：**gpt-6-astra**。仅规划，未执行元数据或测试。

## 原失败和只读核对

R302/implementation/G1-freeze-plugin-native-actual.json 保留完整原调用及 ff5a4a exit1：heredoc第20行 AssertionError，发生于首次输出写入之前。六个目标文件均absent。

实际重复的是全文件 `def after_commit(`（G0/G1均2处）；`context = monkeypatch.context()` 全文件各1处。两者在已唯一识别的 `_b_t2_observe` 片段 b/y 中均各1处，SQL注入代码字节完全相同。独立AST确认该函数唯一；区域外前后字节相同。剩余8个plugin身份映射旧串都恰好1次，未发现其他选择器需要修改。

## 两行修正及执行

plan.json 保存完整 literal authorized_invocation，只将 seam count 从old/new改至b/y，将 seam slice 从old/new改至b/y；其他原脚本逐字不变。绝对解释器、chr(10)、原SHA条件、八处plugin映射和exclusive写入保持。

ROOT核对两行差异及输入pin；Sol重确认六输出absent/non-symlink后执行一次，0 retry。新完整actual存R305/G1-freeze-plugin-native-actual.json，原失败不改。成功后核对六输出SHA、JSON及精确plugin重构，直接进入已有R302 G1源码/native/argv审阅和GREEN接续，不新增通用gate。

## 边界

已实现G1源 SHA `a280954e4774035982661e2fb388af2787691320f396514953720217b4add7a3` 不改；Gtest、runner、HEAD和原五key额度不变。无新测试，不把元数据失败当行为RED。新失败或部分输出保留并停止，不清理重试。元数据成功不能代替GREEN/RPC/T2验收。

所有输入SHA256、实际选择器计数及absence见 plan.json、input-observation.json。
