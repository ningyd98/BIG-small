# R106：P5 原生 domain 描述完整性修复计划

实际作者 gpt-6-astra；实施仍为原 GPT-6.1-sol 单写者。**PLANNED_PENDING_ROOT_ACTIVATION**。本轮只读证据与制定计划，产品/测试/静态/复现/actual/Git 均未执行；不修改已冻结 R100–R105 计划和原件。

## 原失败与准确根因

R105 唯一 inherited GREEN 真实 `exit1`，UTC 2026-10-07T19:16:13.743285 至 19:16:45.078716。完整 JUnit 92 unique：32 P5 FAIL、60 OC1 PASS、0 error/skip；32项统一在测试 callback 前由 exercise:151 报 `ValueError: exact operational descriptor fields required`，没有进入各自行为断言。原 stdout 208536B，SHA `b48dcf3b8fc3d6206f8132216cbe43edc78bd87dd899dd6adcdfac66ec586a3a`；原 JUnit SHA `864111c67f62d6dd605e65f8b74a98b436be464779bd27e72e0a36b15f41451e`。原 R101/implementation/green 与 `/tmp/bigsmall-p5-r101-green`、原CPU原件保持，不删除、不覆写、不重命名来假装未运行。

纯源码/AST检查确认：OC1 `OperationalDomain` :99–128 真实定义27字段；P5 `export_record` 使用 `asdict(self._clock.domain)`，没有删字段。R105 `_validate_domain` :765–794 的精确集合只有24项，漏掉以下**三个真实能力限制字段**：

| 键 | 原生固定值 |
|---|---|
| native_authority | UNAVAILABLE |
| future_horizon | UNKNOWN |
| restart_suspend_hostpause | NOT_TESTED_OC3_GATE |

其余字段集合吻合，没有 validator 多余字段。真实 worker/runtime 创建 `VisualBootstrapDefinition(operational_windows=...)`，其 `__post_init__` 经 `_plain`→`_validate_references`→`_validate_domain`→`_descriptor_fields`，因此合法原生描述反被 exact-set 拒绝。worker捕获并持久化错误，callback未进入，与原32项同错吻合。原输出没有内层产品 traceback；这里是原执行失败加确定的源码矛盾诊断，**不是新执行复现或伪造内层堆栈**。完整分析和命令来源在 diagnosis.json。

Sol终态 source-freeze SHA `b3edc47a1cb6b1610bafe6277c78f29919505e28db5eb0657edbe807557ac31a`，budget SHA `78b80ee0fed77610ae2aac664054c7c5341227f80619cdd7cc346efbfa559578`。十current与各自冻结snapshot已重新只读核对一致。R105 I整理/formatter/delta/Ruff/format各已用1且exit0；GREEN1已用且exit1，旧额度remaining0，无在途命令。本轮给予明确新额度，不抹除历史消费。

## 只改两路径，同一根因

1. `src/cloud_edge_robot_arm/vision/operational_windows.py`：仅在 `_validate_domain` 的精确字段集合加入上述三键，同时在现有 constants mapping加入三个原生固定字符串值。保留 set(record)==expected、所有原类型/域/AGE/HARD/parent/live registry检查。不得改为允许extra、过滤export、使用可忽略字段、默认补缺、任意类型或constant VALID。不可升级三项能力，或把 UNKNOWN/UNAVAILABLE 改成实际支持。
2. `tests/test_operational_windows.py`：只增强原 `test_window_export_preserves_typed_boundary_constraints` 节点，不增节点/参数，不改 startup fixture或其他断言。对真实export逐项断言三键原值，现有 frozen合法decode/当前owner positive继续保留。每键分别生成缺键与伪升级值副本，加入现有malformed循环，同时要求 `_validate_references` 抛ValueError、frozen `_check_reference` UNKNOWN。伪值固定为 native_authority=AVAILABLE、future_horizon=FINITE_CERTIFIED、restart_suspend_hostpause=VALIDATED；再各用True证明不能以布尔冒充字符串。另一个domain未知额外键副本必须拒绝，避免修复悄悄宽松化。所有副本从真实record deepcopy，不修改原live/export。原事后无owner UNKNOWN、所有旧typed/NaN/循环/parent等断言不删。

其余八个P5源、OC1实现/测试、pyproject及原失败文件均保持字节。无需改生产 export、dataclass、bootstrap、worker startup、lease或预算。旧legacy无新字段路由保持；真实原生历史本来包含27字段，不能为24字段残缺描述宣称恢复live能力。

## 实施步骤和有限新额度

ROOT先读计划完整双文件并绑定双SHA，重验30项pins、十源+snapshot、OC1源码与原测试旧pin、原停止预算/原92JUnit。R106 implementation新目录写source-before/semantic-after/format-after/命令原件，不覆盖任何旧implementation。开始前确认 R106/implementation/green 与 `/tmp/bigsmall-p5-r106-green` 均尚未存在；R101旧leaf必须保留。

顺序：精确手工修订两处schema及原测试节点→一次仅两文件formatter→一次新局部delta proof→一次两文件Ruff→一次两文件format-check→一次32P5 GREEN→冻结最终十源和结果→不同作者独审。完整argv见JSON。

- 新formatter最多1次，仅两修改文件；无import新增，不运行自动I整理或其他--fix。
- 新delta proof1次：stdlib AST/tokenize和字节，不import产品。证明生产仅 `_validate_domain` 两个literal各新增三项，函数剩余AST原样；测试仅原typed-export节点增加本计划断言，旧节点/参数及全部其他测试AST不变；八保护源/OC1/config字节不变。format前后完整AST(type_comments=True、排除位置)相同，type-ignore内容/附着语句和COMMENT token文本/顺序保持。该证明是R106 delta，复用R105已有proof，不重跑旧proof。
- 新Ruff1、format-check1，仅两修改文件；其余八源复用R105真实静态通过并以字节pin证明未变。
- 新GREEN1只运行 `tests/test_operational_windows.py`，预计同32 unique、全部PASS/0error/0skip。无RED/单节点探跑/collect-only/额外compile/mypy。
- OC1本轮测试预算0：源码SHA `b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b` 与原测试SHA `ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f` 匹配此前pin，修复只在下游P5描述验证器，复用原92批次中的60个实际PASS。不能把复用说成新运行92PASS；若OC1依赖意外变化则先停重规划，不自行重跑60。
- actual/model/network/renderer/Git/子代理额度0。

每条新命令保存真实argv/cwd/开始结束UTC/有限env/stdout/stderr/exit/SHA。任何计划外失败即停，保留当前源/原件和已消费额度再Astra，不重跑或泛化白名单。不得以模型模拟/静态预测替代32项结果。

## 验收

新schema与真实27字段完全对应且三个能力局限值未升级；合法frozen描述可经真实startup到达callback，缺键/extra/伪升级/错类型拒绝；原32节点实际全部通过，新/旧分母明确分开，原60OC1适用性凭输入hash复用。然后最终十源freeze、独立审查原R100/R101/R103/R105全部语义，才可验收P5软件。

本轮不承诺修完此因后不存在被startup遮住的其他问题；若出现不同失败如实下一轮，不扩大当前计划。P6真实事务/租约/最终dispatch仍独立，旧P4前缀不可借live句柄；actual/formal仍0，不能把软件成功当完整T12完成。后续Git仍按另行明确路径交付并保存两份legacy codec测试依赖，不复制完整raw/DB。本计划发布后冻结，ROOT激活仅追加收据。
