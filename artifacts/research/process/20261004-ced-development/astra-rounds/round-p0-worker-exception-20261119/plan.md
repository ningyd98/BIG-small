# 组件 worker 的异常原件

## 原始证据

- 1803 的 component/episode.json、worker/result.json 只保留 ValueError；step-01 MOVE_ABOVE 在 INITIALIZING、零已执行动作。原 traceback 已丢失，离线 constructor 重放单独记录。

## 实施范围与假设

- 在 sol_molmo_components.py 的组件执行入口及现有异常处理处记录首次异常，区分后续 after 捕获或外层异常；复用现有 episode.json 持久化顺序。将异常类型、可安全公开的消息、实际 traceback（代码文件的仓内相对路径或模块名、函数、行号）、当前执行阶段与可用的 action/step 写入。成功路径及遗留 episode 保持可读。
- 阶段覆盖实际初始化、规划、PRE、servo 初始化、控制器与 POST/收尾，按代码实际边界更新。禁止记录 traceback locals、绝对私有路径、完整请求/响应、环境、令牌或任意异常对象 repr；对已知安全消息做可读保留，对任意带秘密的自由文本采取经测试的安全替换，保留异常类和真实帧。不得因格式化诊断改变原异常处理。

## 运行前置

- 先在现有 component safety/worker integration 测试入口注入无云可控异常，确认原件缺字段；再实施。历史 raw 只读。

## 验收

- 对应真实执行入口的注入异常落盘并从文件独立读出，至少含精确函数和有效行号、原始异常分类、可读安全消息及失败阶段；敏感 sentinel 不出现在新增诊断；after 失败不能覆盖主失败。正常完成及已有 ComponentStopped 路线作对照，原 status/reason、safe_stop、物理结果、shutdown、退出/成本行为保留，定向 pytest 与 Ruff。

各输入的工作树路径与 SHA256 见同目录 plan.json。
