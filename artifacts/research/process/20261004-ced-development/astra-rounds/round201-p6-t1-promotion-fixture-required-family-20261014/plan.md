# R201：promotion fixture 必传 family 修正计划

实际规划者：`/root/astra_status_plan`，`gpt-6-astra`。仅规划，等待 ROOT 门控。

独立有限读取确认：新测试第130行调用 `_frozen._r179_completed(fixture)`，冻结 helper 第3092行签名为 `(fixture, family)`。当前路径是 bootstrap promotion，随后明确发起 bootstrap 的 RESERVE_PLAN；helper 的 bootstrap 分支完成 CAPTURE，其他分支完成 WAIT。因此应显式补 `"bootstrap"`。这是静态接口缺陷，没有实际 TypeError、pytest失败或子退出码，不能作为合法RED。

唯一编辑是新测试 `_r196_promotion` 中该调用改为 `_frozen._r179_completed(fixture, "bootstrap")`。同一 Sol 先完整归档16220 B旧文件，再做一次精确替换。预期增加13 B至16233 B，其他每一字节（包括EOF、12节点/装饰器/断言）不变。原测试、shared、保护源、golden和所有历史证据不改。其他已撤回疑虑不纳入修复。

ROOT正常完整before/after字节和精确diff核对，要求新文件恰等于旧文件的一处上述替换；不建立专用验证脚本、不新增执行槽。通过后仅恢复R196源码准备及原完整test/三脚本门控。六槽仍0/1HELD，RED8/GREEN63和同席新增6批不变；没有任何运行/PASS主张。

完整5输入pin、原始证据、准确输出路径和停止条件见同目录 plan.json。当前R196完整promotion链尚未实证，后续若RED出现其他原因必须STOP交新Astra计划，不通过修改预期绕过。
