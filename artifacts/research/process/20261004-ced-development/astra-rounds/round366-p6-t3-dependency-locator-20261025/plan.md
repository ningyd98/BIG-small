# R366：依赖定位先核实存在性

实际规划者：`gpt-6-astra /root/astra_r363_plan`。仅行政定位修复，新增运行额度0；有效HEAD为`dd9df375e1d372490145327bcbfee5804352fcc4`。

ROOT tool06ac0e与AUTHOR toolb9bc85均exit2：把未经验证存在的conftest传给rg，真实文件匹配正常并不消除读错误。ROOT完整原返回对象来自当时store；AUTHOR文件诚实标为完整可见tool-return转录，不是不可得的原始transport字节。两份原失败均已读取、绑定SHA，保留不改。

有限实际调查确认项目配置为pyproject.toml；tests、项目根和逐级祖先的conftest均不存在。四个R365测试源、tests/__init__、导入的test_operational_runtime_closure和local_temporal、R235显式插件及R196冻结seed均实际存在并已pin。新测试SHA为`51cf42610d1b4c5c6be7594e038e0b54645368763bb38540383a6fb35a8cc437`；seed524867B、SHA`20cbbe651d46f5c62428130db2523a413fcccede2f8851a0e6db2fb56126fb79`。这些是已定位输入，不宣称完整传递依赖或资源证明已完成。

ROOT验收后，ROOT/Sol恢复以下最小流程：先用rg --files和有限显式存在性检查取得真实候选；再仅对存在且可读的文件做内容搜索。隐藏或ignored适用配置须显式检查，不能只凭普通rg未列出来断言不存在。可选文件缺失记ABSENT，不制造空conftest；必需测试/import/seed缺失则停受影响闭合。

rg exit0为有匹配；exit1且无读取错误为本次范围NO_MATCH；exit2、权限、路径race等为READ_ERROR，不能用`|| true`吞掉。空候选列表记NO_CANDIDATE_FILES，不执行裸rg。保留每次退出与原输出，按真实source边有限读取并冻结实际config/conftest/测试helper/seed；沿用已有gate库存，不重建审计框架，不import/pytest/version/collect/DB。

新增dependency-locator-readout.json记录存在性、pins、状态、实际依赖边及UNKNOWN；ROOT另写root-locator-disposition.json并核验原文件未改。本轮不改产品、测试、配置、seed、旧raw/plan/ledger；独立R365 runner准备可继续。

R365的一行范围、四HELD命令、RED→一行→GREEN→三codec→完整UTC、600/900秒及真实资源门槛不变。静态扫描释放不等于运行释放或行为通过。真正必需依赖缺失、其他读取失败或需要修改源码/配置/选择时，仅暂停受影响部分并交实际Astra。
