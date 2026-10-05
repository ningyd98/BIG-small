# R03 实现前根审查

结论：**ACCEPT_FOR_SCOPED_IMPLEMENTATION_WITH_CORRECTIONS**。R02-PIN-01已通过限定独审，允许按原准备稿P1–P4实施source-only RESET prefix；实际prefix必须另经软件独审、来源与预算冻结后由root唯一启动。原preparation.md/json保持历史原字节，本审查不执行或证明真实RESET、UTC、校准组或consumer准入。

接受真实startup application→SQLite job/lease/open attempt→poll_once→planner_factory之前的专用分支。role_binding可为None，但必须有确切活跃应用/worker/capture/backend/executor注册；公开dataclass、复制catalog、同路径外来repository或调用方native布尔不产生授权来源。沿唯一现有recorder tee保留RESET BEGIN/END、真实clock pair、原120 SETTLE、全部原始操作和失败；冻结整个slab后才发B，发布前再在真实lease guard内重读来源。未adopt的prefix不得绑定RawV3 owner或冒称任务执行。

## 两项必须修正

1. **缓存相机原件不能省略。** 实际backend.reset在当前backend.py第552行调用_update_sensor_frame，step在第604行同样调用。borrowed capture本身不主动render，不代表整个RESET/SETTLE没有相机调用。有observer时缓存CAPTURE可能产生真实RGB/depth/segmentation pass，必须保存其原始事件、帧、失败及分母并实测计数。零explicit RGB-D acquisition、零planner/model/action request与零renderer不同；禁止为得到零计数而关RGB、关noise、改cache或从slab删除原件。默认320×240、原noise与当前资产保持锁定。
2. **历史slab上界不能充当未来now上界。** A/B仅包围B发送前已冻结的事件与pairs。B verification之后任意时刻的current_time仍需要独立可信UTC/rate来源；不能把U_B直接接入后续consumer。首prefix只报告历史条件区间及原TTL/deadline的必要宽度下界诊断，不输出真正consumer可行性、finite native now或连续未来证书。6秒software fixture大于默认5秒TTL是软件诊断，真实宽度仍待原件；门槛不放宽。

对应CPU检查应覆盖实际缓存CAPTURE的完整分母、sole observer和原始tee，复制/漂移/失lease拒绝、A→RESET/SETTLE→freeze→B顺序、freeze后事件保留为失败、当前UTC仍UNAVAILABLE，以及planner_factory未触达。CPU backend/network效果须标SOFTWARE_ONLY，不能混作actual计数。失败exchange也保留attempt，无自动第三次请求、重试或同output重入。

## 外部时钟政策

已重新核对[Cloudflare官方概述](https://developers.cloudflare.com/time-services/roughtime/)及[官方地址/公钥和beta说明](https://developers.cloudflare.com/time-services/roughtime/usage/)（2026-10-05读取）。官方说明定位为粗粒度认证时间，并标示beta和根公钥可能变化；地址roughtime.cloudflare.com:2003及当前公开key应在新config明确冻结。由此不能推出本项目获得0.005秒UTC保证或独立计量校准，签名验证也只证明受信key的响应。固定draft08/version/key失败时保留原失败，不静默降版本或切key。issuer_accuracy仍UNVERIFIED，native UTC与consumer current-time界仍UNAVAILABLE。

此处是公开官方材料的限定推论，不宣称服务器在所有环境均不可达或不能提供其他精度保证。尚无实际A/B响应或本地UTC校准原件，本轮network/UDP/model/renderer/physics均0。

## 范围与后续

仅新research模块/tests/薄CLI/原始config，以及worker startup attachment和早期分支。dispatcher、service、vision/execution.py、Task2、现recorder合同及旧raw不改。先独审新软件，再一组source-only真实prefix测可用性，之后才判断至少9独立支持组；R01标记诊断和R07离线生产仍可独立推进。已有全部研发授权允许实施，不另请求用户批准。
