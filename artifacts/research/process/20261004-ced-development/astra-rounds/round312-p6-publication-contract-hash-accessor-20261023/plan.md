# R312：Publication contract_hash 只读访问器修复计划

**实际模型：gpt-6-astra。仅规划，未执行。**

## 已确认问题

源码确认 legacy/local 两个publication类缺少 `contract_hash` 属性，而产品 `worker_runtime._local_generic_mutate` 与原writer测试均读取它。该字段已经由各自codec校验并持久化；这是实施前接口缺口，尚无实际运行AttributeError，不能冒称失败基线。原R311已冻结，按新根因另立本轮。

## 最小修改

仅 `repositories/event_autonomy/visual_owner.py`：

- legacy `VisualOwnerPublicationRecord.contract_hash -> str` 返回 `str(json.loads(self._payload_json)["contract_hash"])`。
- local 子类覆盖属性，返回 `self.string("contract_hash")`。

两个只读property放在各自original_plan_hash附近；构造器、schema、codec、序列化/digest、预算、权限和调用者均不改。输入SHA与精确源码见JSON及input-observation。

## 有限RED→GREEN

- [ ] 实际Sol先新增 `tests/test_publication_contract_hash.py::test_publication_contract_hash_readonly` 和R302 compact runner的本轮身份副本。ROOT读完整源码/argv；新两键observer_red/green各一次，child120秒、outer240秒、0retry。
- [ ] 微回归只读取两份已冻结真实通过fixture：R166 legacy golden、R196合法baseline中的local publication。必须真实codec解码，不调用旧复杂fixture、不构造worker/时钟/repository。两案例都保存读取前后payload/digest、预算/原时间字段、权限registry不变证据。
- [ ] RED应精确因两个已合法解码对象均缺少contract_hash而失败；一节点内收集两个AttributeError并finally保存case。其他异常不能算合法RED。ROOT接受后才允许两个property修改。
- [ ] GREEN一次：精确值、重复读取、detached roundtrip、导出副本隔离、赋值拒绝及缺字段/非法SHA仍拒绝；序列化/digest/原预算/权限registry保持。原RED和源码全字节原件保留。

## 接回R311与验收边界

ROOT接受GREEN及仅两个新增property的精确差分后，独立新generation-map将唯一visual_owner旧SHA映射到实际新SHA；R311旧plan/input一字不改，新gate/ROOT acceptance绑定该例外与所有其他旧源一致。若旧gate已准备，先存完整before/mode再CAS更新引用。R311四once仍未用，不新增或刷新额度，随后按原计划逐项释放。

旧wait2/dual/observer3保持原运行世代事实；因其实际场景不调用新访问器且相关代码未变，ROOT可在精确非重叠证明后复用，不重跑也不称其是新源码实际运行。新微回归与R311四节点提供本轮变化证据。fresh T2审阅后置，不能直接晋升整个T2或进入T3/P6C/native。

任意新根因/范围扩大或计划外失败保留实际并停止相关修复，另交Astra。交付沿明确路径commit/push及三SHA核对；规划席位未测试、未实施、未Git写入。
