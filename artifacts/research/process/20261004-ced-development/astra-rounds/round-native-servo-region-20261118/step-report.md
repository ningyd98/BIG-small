# 搬运区视角恢复重放结果

**候选未通过，暂停并交下一轮 Astra。** 原 `native/fixed-01` 的结果和已用的 4 次 Molmo、1 次 Sol 保留。两次重放均完成规划，并在第 5 个动作 `MOVE_TO_REGION` 的物理步 3952 结束。两次各回放 4 条原始 Molmo 文本及 1 条原始 Sol 响应，实际模型载入、生成及付费请求均为 0。

## 原件及 RED

- 复核原证据清单中的 1806 个文件，字节长度与 SHA256 全匹配。Astra 的 85 个输入在 RED 前全匹配。候选实验后仅组件候选接线 SHA 发生预期变化。相对原生运行，H1 的入口变化只将同一个资源准入 helper 改为从新模块导入。重放直接调用现有桥接器与 SQLite worker，其渲染通过同一 GPU 锁准入。
- 原始与重放均使用 seed 42001、相机 `[0.35, 0.0, 1.35]` 和原 75 mm 标记资产。新场景的初始与云后 RGB PNG 分别逐字节匹配归档，Molmo 查询短语和哈希一致，返回绑定到了各自的新帧身份与真实采集时间。Sol 请求体与归档解析一致，响应逐字节一致。模型协议用归档替身，MuJoCo、OpenCV、SQLite、worker、控制器、SafetyShield 和独立物理评分按生产路径运行。Python 网络调用审计无尝试，模型构造器也无调用尝试。
- RED 重现 `CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED`。第 5 动作从 3112 运行至 3952，最后成功控制采样在 3944。最终右帧的 RGB、深度和有效掩码均与原件逐字节匹配。离线验证仍拒绝右帧。投影区域 2088 像素，4 个当前角点有效，489 个缺色像素全部具有有效深度，其中 321 个符合高前景，168 个无法解释为前景，0 个符合低侧壁或混色边缘。

## 候选源码实验的最终采样

唯一产品改动将 `MOVE_TO_REGION` 加入已有完整候选列表的分支。候选声明顺序为总览、左、右。当前视角为左，已有过滤器将左排除，因此物理步 3952 的两次实际切换为总览、右。以下三帧均实际采集于 `sim_time_s = 16.466666666666054`，各自有独立帧身份及标定绑定。

| 采样 | 相机位置 m | 标记与区域证据 |
| --- | --- | --- |
| `sample-0105`，当前左视 | `[-0.0541935856354791, 0.19603483501869393, 0.6]` | 在线拒绝 `servo registered marker geometry unavailable`。离线标记为 `known_marker_not_observed`，区域本身有 3/4 的当前角点。 |
| `sample-0105-view-01`，新总览 | `[0.11700803934240742, 0.3819805808849465, 0.653875236294896]` | 标记可见。在线和离线均拒绝 `region_current_corner_anchors_insufficient`。投影 3403 像素，2454 个可见平面色彩像素，4 角支持依序为 `[true, false, false, true]`。 |
| `sample-0105-view-02`，新右视 | `[0.6601011560527992, 0.19603483501869393, 0.6]` | 标记可见且 4/4 角有效。在线和离线均拒绝 `region_missing_color_not_explained_by_foreground`，167 个缺色像素未取得合格前景证据。 |

步 3952 的命令序 622–626 依次为切总览、切右视、两次保持、紧急停止。工程记录显示三帧间没有物理步推进或关节目标下发。候选右视的 RGB 和有效掩码与原件一致，深度有 62,262 个像素变化，最大绝对差 0.006183505 m。原件和候选各自执行了严格判定。

候选保留了 0.1056172488 m 抬升、3.1875 s 持物和 0 s 稳定放置，独立物理成功为 false。唯一原源码 RED 和唯一修后 GREEN renderer 运行已用完。全视角拒绝时的保护停止有实际命令证据。修后正例和其余限定回归尚未完成，余下 6 个真实 episode 暂停，等待下一轮实际 Astra。

## 证据位置

- 原生运行及冻结证据清单位于 `experiments/results/phase9/real-harness-20261118/native/fixed-01/`。
- 两次重放位于 `experiments/results/phase9/real-harness-20261118/native-servo-region-replay/`，含 `renderer-command.sh`、`red.log`、`red.junit.xml`、`green.log`、`green.junit.xml` 及各自完整本地 raw。
- 原件与候选像素、标定及掩码分别位于重放目录下的 `archived-pixels-final/` 和 `candidate-pixels-final/`。离线参考以原采集时刻建立，原观测时间与字节保留。报告没有把历史几何诊断作为在线 TTL 的通过证据。
- 同目录 `step-report.json` 记录重放原始结果、命令及派生报告 SHA256。正式研究 `NOT_ACCEPTED`，新增合格分组 0，真机 `NOT_STARTED`。
