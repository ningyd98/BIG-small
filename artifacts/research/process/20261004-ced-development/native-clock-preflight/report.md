# 本机时钟来源只读预检

本机服务报告NTP已开启并同步，systemd为255.4-1ubuntu8.17。已保存四条只读命令的原始输出、SHA和本地monotonic/UTC前后括号；未修改时钟配置或触发新外部查询。该次D-Bus消息客户端往返为 389599 μs，而显示root distance为 4057 μs。

版本化[systemd 255实现](https://raw.githubusercontent.com/systemd/systemd/v255/src/timedate/timedatectl.c)分别计算客户端往返与上游root_delay/2+root_dispersion；后者不能单独当作本机全部UTC误差。发行版255.4补丁的完整源码尚未逐字绑定，本消息也未绑定每个采集pair或真实reset原件，故external UTC uncertainty保持null，不授予校准来源或native权限。后续独立clock协议须保留实际独立每pair括号和原reset journal关联，不能用同步标志、配置5秒阈值、nominal offset、jitter或上游root distance代替。

[命令、原输出哈希和精确字段](report.json)。此预检没有模型、物理、渲染或解码调用，也未修改历史试次/源码/消费者。
