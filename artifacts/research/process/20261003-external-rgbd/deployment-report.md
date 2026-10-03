# 第三方真实 RGB-D 数据部署阶段报告

快照：2026-10-03T04:39:00.677227+00:00。总体状态 `REAL_DATA_NOT_VERIFIED`。用户最新要求：中国大陆镜像下载，不走隧道。数据根绝对路径、来源版本和断点详情见 [JSON 报告](deployment-report.json)。

后续更新：用户授权“精选集先用”后，独立魔搭变体已完成 10 场景、40 帧真实 RGB-D、5 组预览和 CPU 0/2 worker 验收，为 `CURATED_RGBD_VERIFIED`；见[最新精选验收](../20261003-curated-rgbd/acceptance.md)。本页保留原完整目标的历史快照，以下阻塞及 0 数量仅指原两完整目标。

## 当前结论

没有恢复大文件下载。GraspClutter6D 的完整固定版本尚无已核准大陆镜像，保持 `BLOCKED_NETWORK`；已有 3,241,373,523 bytes（约3.24 GB）断点全部保留。RoboMIND 官方魔搭可通过物理网卡直连，但完整目标远超首轮预算，保持 `BLOCKED_BUDGET`。两套数据均无完整 raw、真实 batch 或真实样本预览，范围仍为 `NOT_VERIFIED`。

| 来源 | 固定 revision | 实际状态 |
|---|---|---|
| ModelScope X-Humanoid/RoboMIND | be28d59219430dc8796f221f7fc4c23e113d6a4e | 目标轨迹0，BLOCKED_BUDGET |
| HF GraspClutter6D/GraspClutter6D | 973a567efa2f8047e5a40c9113a672e8215bcc1b | 完成场景0，BLOCKED_NETWORK，断点3.24GB |

## 大陆镜像与直连证据

[hf-mirror.com的9个固定文件](sources/mainland-mirror-candidates.json)均302转到HF Xet海外目标。hf-mirror.net的小请求可从物理网卡直连且长度相符，但该站声明全球Cloudflare节点，尚无大陆托管证据；没有启用为大陆文件源。魔搭搜索只找到Voxel51精选演示发布，和当前完整9归档的版本与格式不同，不能自动替换或混卷。官方作者入口及定向国内镜像检索尚未找到同版本完整文件源；此结论不宣称全网永不存在镜像。

此前同文件小请求曾证实系统策略进入Meta TUN并选择日本代理；历史已下载字节的逐条出口无法追溯，原下载进程已不存在。用户提出新要求后没有恢复该路径、没有修改全局代理/节点/系统路由。

新下载入口强制物理网卡直连：DNS和TCP都在连接前SO_BINDTODEVICE绑定enp7s0并读回确认，拒绝系统DNS、环境代理、假IP、缺策略和未核准重定向，保留原域名SNI与TLS验证。官方HF凭证不会发给第三方镜像。实际[新入口小请求](strict-direct-probe.json)确认ModelScope HEAD200、本地物理接口绑定；hf-mirror的海外跳转在建立海外TCP连接前被阻止。探测未读取归档数据体。只设置HTTPTransport.socket_options不足以保证连接前绑定，当前桥接库按实际httpx0.28.1/httpcore1.0.9锁定。

[独立网络审查](network-policy-review.md)确认真实入口缺网络配置时不回退SDK/系统路由；旧SDK单元测试兼容只用于明确synthetic_fixture来源和mock，不能证明真实下载验收。

## 软件验证

181项离线软件测试通过，6.59秒；[Ruff](mainland-final-ruff.log)及[13个源文件mypy](mainland-final-mypy.log)通过。网络传输包含33项离线测试，整体包含原数据读取、校验、隔离、分卷/原子恢复、分组划分和GT隔离；总数181是完整集合，不与局部测试数重复累计。[既有F1–F5复核](final-rereview.md)已关闭，新增网络审查无剩余必要问题。

相关旧路径上一轮回归122通过/1失败（55.34秒），失败为既有中文注释审计默认路径遗漏output/doc；[基线证明](existing-audit-failure.json)及[回归日志](related-regression.log)保留，本轮网络变化没有重新运行此旧回归。真实集成测试2项跳过，不能计入真实通过。

## 范围与恢复

RoboMIND目标h5_franka_1rgb的两个任务需要68分卷、720,810,482,287bytes（671.31GiB），最小完整任务也超过10GiB首轮及250GiB全局预算。未下载目标轨迹、混用版本、改机械臂或用小示例代验收，HF gated条款未代接受。GraspClutter6D必要9文件总计209,947,108,139bytes（195.528GiB），场景5卷必须齐备；当前仅4项断点，不是可用场景。

确认大陆完整文件源后，配置明确HTTPS镜像endpoint及各跳转域名，并保持同一来源/revision/逐文件SHA256；再运行：

```bash
.venv-data/bin/python scripts/rgbd_data.py deploy --dataset graspclutter6d --profile smoke --num-workers 2
.venv-data/bin/python scripts/rgbd_data.py status --dataset all
```

当前deploy实测退出3，分别给出BLOCKED_BUDGET和BLOCKED_NETWORK，无新增归档数据字节。[部署说明](../../../../docs/rgbd_datasets_deployment.md)记录配置、命令与目录。缺单位/K/对齐/基座外参/时序不补造；真实预览、CPU0/2worker和划分审计通过后才升级verified_scope。模型训练、抓取基准、动作成功、闭环控制与Sim2Real均未运行。
