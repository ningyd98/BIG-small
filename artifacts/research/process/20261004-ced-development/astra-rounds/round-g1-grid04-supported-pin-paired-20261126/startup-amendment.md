# startup-amendment.md · grid-04 无针 CPU 前缀启动勘误

实际规划模型为 `gpt-6.2-astra`。本勘误仅修订 `supported_pin.py::prefix()` 的包来源登记。复核时该文件 SHA256 为 `9351051beb5189b1c667a0809d4147a1928d76b2b03b63a7bf73e2da6ac6b9e5`。原计划和上次勘误的四个文件均保留原字节，摘要见配套 JSON。

**原始失败。** 实现者报告 `verify_sources`、`validate_prefix`、`verify_imports` 已通过，随后 `version("scipy")` 抛出 `PackageNotFoundError`。源码确认该查询位于第 82 行，早于第 98 行创建私有输出目录和第 101 行创建 attempt。只读核查时私有输出目录仍不存在。实现者报告本次 RESET、命令、积分和曝光均为零。保留此次启动失败及修订前代码摘要。

**最小修复。** 删除发行版查询元组中的 `scipy`。原计划未登记 SciPy，当前前缀未导入它，无需安装。保留 MuJoCo、NumPy 的原版本断言、Pydantic 的版本登记和已有来源校验。OpenCV 分开记录两项：已加载模块 `cv2.__version__` 为 `4.14.0`，实际提供它的发行版 `opencv-python-headless` 的 `METADATA` 版本为 `4.14.0.94`。当前源码只读取 `cv2.__version__`；新增发行版记录时应使用实际提供者。无需查询 `opencv-contrib-python`。

**复核与首次运行。** 修订后登记代码的新 SHA、实际启动解释器及二进制 SHA。对四个实际依赖记录发行版名称、版本、`METADATA` 路径及 SHA256，并记录运行中模块 `__file__` 的解析路径及文件 SHA256；OpenCV 另记同一提供者的 `cv2/cv2.abi3.so` 路径及 SHA256。继续核对冻结后端、光学模块与轮次程序来源。原输入预检重新通过、私有输出仍不存在、计数均为零时，使用原独占创建流程登记 attempt，允许**第一次实际 RESET**。原无针 CPU 上限仍为一次前缀、1 RESET、236 条原命令、1520 个积分步、0 渲染、0 曝光。实际 attempt 已存在或计数不符即停止，保留现场。

原 RNG 首败及 `CLOSED_FOR_THIS_ROUND` 维持有效，四个配对槽均保留未执行状态。正式、整机、独立评分、硬件和远程均为零。本次只读核对未运行测试或前缀。
