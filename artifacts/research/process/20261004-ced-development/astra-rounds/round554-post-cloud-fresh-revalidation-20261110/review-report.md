# R554 independent whole-change review

Base `ae9cbf0b6bb5330de799004c664749ee462c3329` → HEAD `9f7e7064e2e5ba204517af95d5832330ad45112d`，三个提交。按 requesting-code-review 模板审查完整差异、R554 request/design/plan、R555/R556计划及账本，未派生子代理，未修改生产源码或Git。实际模型/生成/付费/硬件调用均为0。

## Strengths

- 严格JSON、技能白名单、非空/顺序及上下文检查先于唯一supplier调用；异常不回退旧几何、不重试云端。
- CLI在模型加载后持有同一MuJoCoCaptureSession，补帧真正调用capture；两套raw分别保存并纳入清单，没有用元数据重写旧帧。
- 重跑两次独立绑定定位及原有几何/跟踪，比较角色分离的support mask；三种深度残差是独立工程异常门，没有伪称物理身份、稳定性或校准误差界。
- R555在三种终态同步权威refresh状态；R556只整理测试导入。观察器保留原process/_post对象与参数，付费开始前独占写入并fsync，失败占预算。

## Issues

### Critical

无。

### Important — R554-REV-1：最终返回边界未复核新帧

位置：`src/cloud_edge_robot_arm/vision/grounded_planner.py:465`；相关 `src/cloud_edge_robot_arm/cloud/planning/pipeline.py:476`、`:728`、`:741`；覆盖缺口 `tests/test_molmo_grounded_planner.py:860`。

适配器最后 `_fresh` 只在返回PlannerDraft前检查；原管线随后才完成语义验证、可信字段和真正的build_task_contract，且相同请求cache hit直接返回历史响应。现有过期测试仅延迟适配器build_grounded_contract候选构造，没覆盖实际合同构造。这是计划冻结pipeline后遗漏的同一最终接受边界，不声称本轮修改了冻结文件。

只读CPU原始复现：委托原pipeline.build_task_contract后把fixture时钟推进6秒，返回 `PLANNED`、非空contract、validation.passed、refresh.status=PASSED，新帧龄6.0秒。再次执行逐字输出一致。另两例命中同请求缓存：新帧龄6.0秒，或timeout_s从30改31，仍直接返回同一PLANNED响应对象。每例仅CPU桩1次cloud、4次query、1次refresh；没有真实调用。

影响：实际接受结果可能已过5秒门，缓存命中也跳过当前绑定门，未达到“最终拒绝过期合同”的验收边界。建议下一轮实际Astra评估仅显式post-cloud路径的最终准入回调或等价机制，携带可信新帧和原绑定，在实际合同构造后、缓存PLANNED返回前复核；失败contract null，保留历史证据，不重复采集/生成/付费、不放宽TTL。增加真实pipeline合同构造/可信字段耗时及缓存有效/过期/绑定变更回归。不得在当前冻结约束下直接扩大修复。

证据：`review-evidence/original-command.sh.txt`、`original-output.log`、`reproduce-final-contract-expiry.py`、`recheck-stdout.log`，以及 `cached-original-command.sh.txt`、`cached-original-output.log`、`reproduce-cached-return.py`。原始工具chunk分别c62f86、e3e010。两个manifest记录脚本、输出和输入文件SHA256。

### Minor

无。

## Review focus / validation

前四项review focus得到代码与相关测试支持：解析/上下文先于采集；CLI真实同会话调用而非缓存；depth max/RMS/mean独立边界；角色mask变化和既存同色歧义门。第五项仅在适配器候选构造内得到覆盖，实际pipeline最终返回及cache存在上面的Important缺口。

已读456PASS相关CPU、14PASS采集会话、5PASS观察器、26PASS CLI（包含于456）、Ruff输出；全量一次实际94PASS/1FAIL，既存中文docstring失败保留。独立核对HEAD、六个冻结core SHA和git diff --check通过。未重跑庞大测试；CPU新增复现不写仓库测试或生产文件。

## Rulings considered

1. 用户继续授权且无需第二确认：request/design/限定预算支持，接受；不能据此绕过本次审查阻断项。
2. float32测试以阈值上下1um取值：接受，生产严格比较没放宽，独立阈值上下界充分；不能扩大成误差保证。
3. provider无close API，以独立真实进程退出释放：接受该专用进程边界；CPU cleanup不是GPU释放证据，保留资源可能存活到退出的成本。
4. 全量一次maxfail=1/180s：接受用于分类，不能宣称全量绿或覆盖首个失败之后的测试。

## Declined to judge

- 实机身份、连续稳定性、动作效果和正式研究：明确在本轮暂停MuJoCo开发范围外。
- 恶意supplier完全伪造合法字节/ID/时间：计划明示受控CLI.capture是可信边界，载荷本身不能认证曝光。
- 实际Molmo/Sol成功与当前GPU/ABI/资源准入：本审查没有真实执行，仍需运行前检查。
- 既存中文docstring失败修复及全量首个失败之后的健康：冻结基线问题且计划禁止无关修复；不作全量绿判断。

## Assessment

**Ready to merge: No。真实运行：暂不可进行。** 仅发现一个Important根因，包含实际最终构造和缓存返回两个出口；无其他Critical/Important或Minor。先汇入下一轮实际Astra计划并完成限定修复、CPU回归和证据，再解除真实运行门。剩余1load/4gen/1paid预算未使用，原历史累计3/6/1不变。即使修复通过，真实合同和物理/正式研究仍需分别记录，不能以软件测试替代。
