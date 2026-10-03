# 大陆来源与物理接口直连：新增网络入口独立审查

日期：2026-10-03。范围仅为新增网络政策：`network.py`、`transfer.py` 的传输入口、`deployment.py` 的 plan/doctor、CLI 与默认 YAML。没有修改实现文件，没有重做完整代码审查，没有执行真实数据下载。当前保留的约 3.24 GB partial 不在本审查中改写。

## 结论

**审查发现的真实下载入口遗漏已关闭；本次范围无剩余必要 finding。** 当前默认配置不允许 GraspClutter6D 使用未核准镜像或退回官方海外文件端点：`hf_endpoint: null`、空允许域名与明确 `blocked_reason` 使其返回 `BLOCKED_NETWORK`。RoboMIND 保持官方 ModelScope 来源、精确允许域名与既有预算门禁。候选来源记录尚未核准大陆完整九归档镜像，审查不把镜像 HEAD 可达性或启动下载当作真实部署验收。

## 已关闭的入口遗漏

初始版本仅在 YAML 含顶层 `network` 时把策略写入 plan；缺策略时 `_network_reason` 返回 None，旧 SDK/普通 HTTP 客户端可被真实来源计划使用。临时本地 mock 复现曾得到 `policy=None`、`COMPLETE` 且旧 SDK 被调用，没有访问远程。

修正后 `prepare_plan` 始终写入网络策略；缺少 `direct` 策略的真实计划被拒绝。再次使用省略顶层网络配置的自定义 YAML、原始 GraspClutter6D 九归档固定清单：

```text
repo: GraspClutter6D/GraspClutter6D
revision: 973a567efa2f8047e5a40c9113a672e8215bcc1b
files: 9
plan status: BLOCKED_NETWORK
reason: Only explicitly configured physical-interface direct downloads are allowed
download: BLOCKED_NETWORK: plan gate rejected transfer
```

该探针把旧 SDK 设置为一旦调用即报错，仍在门禁前被拒绝。旧 SDK 测试路径仅保留给同时标记 `sample_provenance=synthetic_fixture` 且 repo 以 `synthetic_fixture/` 开头的明确夹具；当前真实来源清单不满足这一条件。它是本地 mock 单元测试兼容分支，不用于本次真实数据下载，也不作为直连或数据验收证据。

## 核对的实际路径

- 直连模式一律使用专用 transport 与 `trust_env=False`，包括小 HF 文件，不回退到 `hf_hub_download`。HF 只使用 SDK 的固定 revision URL 构造功能；镜像域名不会触发 HF token 读取/发送。
- DNS UDP 与 HTTPS TCP 均在连接前设置、读回确认 `SO_BINDTODEVICE`；检查 Linux 物理网卡身份，不使用 Meta/TUN、环回、系统 DNS、环境代理或 UNIX 代理套接字作为回退。权限或绑定失败关闭传输。
- DNS 使用显式数值 resolver，通过同一物理接口发送；拒绝 fake/private/reserved IPv4、错误来源、事务/问题不匹配和畸形响应。协议/地址政策错误不换下一 DNS；仅有限的 I/O/超时重试仍使用明确配置的物理接口 resolver。
- 每次实际请求和跟随重定向都检查精确域名、HTTPS/443 和 URL 无凭证条件。未知 CDN/海外重定向在接触该目标前被拒绝。TLS 保留原允许域名的 SNI，证书/域名校验开启，禁止不同 SNI 覆盖。
- `doctor` 的网络检查也使用直连 transport、`trust_env=False` 与逐次请求域名门禁。默认被阻塞的 HF 镜像不发请求。独立本地 mock 探针只观察到 `modelscope.cn`，随后未知 HTTPS 302 被拒绝，未接触未知域名；离线 doctor 不联网。
- 固定来源、revision、SHA256、partial identity 与预算逻辑继续使用上游身份；镜像仅改变传输端点。没有把第三方镜像当作不同数据版本混卷，也没有发送 HF token 给镜像。

## 执行的局部检查

```text
.venv-data/bin/python -m pytest -q tests/test_external_rgbd_network.py tests/test_external_rgbd_transfer.py -k 'mainland_source or direct_mirror or bind or redirect or dns or physical or fixed_addresses or invalid_policy or virtual_loopback or tls_sni'
38 passed, 31 deselected in 0.57s

.venv-data/bin/python -m pytest -q tests/test_external_rgbd_transfer.py::test_real_plan_without_direct_policy_cannot_fall_back_to_sdk tests/test_external_rgbd_deployment.py::test_doctor_never_uses_system_network_or_unverified_mirror
2 passed in 0.22s
```

第一次检查在无策略入口修正前完成，覆盖已配置的 direct 路径；第二次检查和真实固定清单 dry-run 探针针对最后的入口修正。`network.py` 冻结后实现代理另报告该模块 33 项测试通过；此数字是实现代理提供的记录，不冒充本审查重新运行的计数。

所有故障探针与测试使用临时目录、本地 mocks 或合成 socket 边界；没有利用隧道或远程下载进行复现。没有全套测试或真实 RGB-D 下载/解压/读取验收的新增声明。允许域名代表明确核准的目标，不能单凭域名格式或 DNS 可达性证明服务器位于中国大陆；当前未核准 Grasp 镜像继续保持阻塞，正是该证据边界的结果。
