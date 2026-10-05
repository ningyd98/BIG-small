**2026-10-05 独立复审：REQUEST_FIX（P2 嵌套 marker 构造契约）**

复审对象为 `vision/marker_association.py`、新文件 `tests/test_marker_extent_integration.py` 和 `configs/research/ced_marker_registration_v1.yaml`。没有修改产品代码、测试或登记，也没有调用物理、渲染或 provider。

新文件实际收集 **7 个 pytest 用例**，不是 12 个；结果 **7 passed in 5.93s**，见 [独立测试日志](independent-review-tests.log)。最后一个用例在原始 9 份 `AFTER_*` 遮挡帧上逐一复核，全部保持 UNKNOWN、空边界支持、`extent_complete=false` 与 `NOT_ADMITTED`。未运行原 101 项组合或全仓测试。

**P2：公共 `MarkerObjectRegistration` 构造/replace 未校验并重建嵌套 `PoseMarkerRegistration`。** `marker_association.py` 的 `__post_init__` 直接读取 pose marker 字段并保留其引用。使用具备真实初始字段、固定原始 `digest()` 的可变 carrier 后，外部将 `marker_size_m` 从 0.045 改成 0.0525：登记 digest、原始 context 与 `sources_valid()` 保持有效，两次真实 replay 都为 `OBSERVED_CANDIDATE`，但投影 tag 假设已改变。该结果破坏同一登记输入的不可变性。见 [精确软件反例](independent-review-direct-constructor-counterexample.json)。

`load_marker_registration` 始终构造真实的冻结 marker，因此通常 loader 路径及下述七项实测边界用例通过；反例针对公共具体登记对象的直接构造边界。没有发生原生准入、完整范围或数值界提升。建议在首次字段读取前要求精确 `PoseMarkerRegistration` 类型并重新构造/校验该对象，追加限定回归后独立复核； reviewer 未改产品代码。

对新实测轮廓/深度路径没有发现额外归属或权限提升问题：

- 实测边界从原始 requested-color 外轮廓提取并与原色像素相交；外邻域必须在该轮廓外，未用投影 face、补洞或完整几何假设替代实测支持。投影 tag/quiet/face 仍独立置于 `region_hypotheses`。
- 边界和邻域逐像素保存原始 RGB、光轴 z 深度、世界估计点及标记平面的有符号残差。有效深度检查涵盖投影 face 外的真实邻域；缺深度和外轮廓裁边分别拒答。正邻域深度只报告测量，不提升完整范围或深度分离证书。
- 观测 checksum、episode/scene、标定、相机 profile、完整任务目标、角色/context、登记与资产均沿现有诊断绑定校验。独立反例核对确认异观测身份被拒绝。
- 六份登记 source/asset hash 全部匹配当前原件。**结果**的 mask 字节、嵌套 RGB-D 支持和 coverage 脱离调用者别名并只读；这项 PASS 不替代上述登记中 pose marker 输入的不可变性修复。独立检查同时核对两份实测 mask hash 与一个原始相机反投影样本。
- `whole_target_identity_status` 和稳定性仍 UNKNOWN；所有几何、线速度、角速度界仍 None。`extent_complete=false` 与 `admission_status=NOT_ADMITTED` 保持不可通过普通构造/替换请求提升的输出约束。

源码、登记和测试的 SHA256，以及上述 7 项附加独立检查保存在 [检查记录](independent-review-checks.json)。本复审不验收相机测量真实性、完整物体范围、标定误差、连续运动、原生提交或任何方法准入；原始采集及后续真实试验由主代理独立负责。

**修复后独立复审：PASS，原 P2 CLOSED（限定软件诊断）。** 此结论仅针对下述最终源码，取代首轮 REQUEST_FIX 的当前状态；首轮七项边界 PASS、原始反例及发现文字保留为历史证据。

owner 确认其 50 项组合完成、源码/登记安静并提供最终 hash 后，本次仅独立运行 `tests/test_marker_extent_integration.py`：**8 passed in 6.64s**，见 [修复后独立测试](independent-review-fix1-tests.log)。它覆盖原七项实测边界及全部九份遮挡控制帧，并增加公共构造的可变 carrier、子类、伪造字典与真实对象脱离别名的限定回归；没有重复 50/101 项组合或全仓。

`__post_init__` 现在在首次字段使用前要求精确 `PoseMarkerRegistration` 类型并以 `replace()` 重建校验。按原始可变 carrier/原观测/原 context 再执行反例时，0.045 和 0.0525 两次构造均在几何调用前以相同原因拒绝。真实 marker 重新登记后与调用者实例分离，外部伪造调用者字段不改变已登记参数或 digest。六份 source/asset pin 均匹配；正常 loader 路径的候选仍 `NOT_ADMITTED`、`extent_complete=false`，完整身份/稳定性 UNKNOWN，全部几何、线速度、角速度界为 None。详见 [精确反例复核](independent-review-fix1-counterexample.json) 与 [最终复审记录](independent-review-fix1.json)。

最终 hash 在独立测试与反例后再次核对：

- `marker_association.py`：`f538c6b751ab560b2523cfbe2d237f8956b092931af276bfcda744d10ee4f426`。
- `test_marker_extent_integration.py`：`b0955a6b4ff9942c0a8ec1f26b570757b583e24eea864da036e2c43e34c9dca1`。
- `ced_marker_registration_v1.yaml`：`209a133c05d5b98f940bf9467133ea24120cbb946083dbbb80309cc022172605`。

reviewer 没有修改产品、测试或登记，没有新采集、物理步进、渲染或 provider 调用。该 PASS 不验收测量真实性、完整体积/范围、连续运动、标定误差或原生/研究/执行准入。
