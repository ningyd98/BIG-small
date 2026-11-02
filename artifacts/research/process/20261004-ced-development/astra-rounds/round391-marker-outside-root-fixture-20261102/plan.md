# R391 真正仓库外 registry 负例输入修复

实际规划模型 gpt-6-astra；代理 /root/astra_r389_revalidate；2026-11-02T11:21:26.261460+00:00。

结论：确认是测试输入位置假设失效，仅准修复outside_root负例；不改loader。等待R378独立pose/asset guard终态清理和单writer移交后实施。

## 原始失败与根因

R378 marker_complete_green真实执行17.226秒，52项=51PASS/1FAIL，0error/skip，source_drift/errors/live空，已reaped。失败为test_registry_path_must_be_regular_under_root_without_symlink_ancestors[outside_root]：原pytest.raises(ValueError,match="registry") DID NOT RAISE。

只读核实原fixture是普通文件、无symlink祖先、resolve实际位于ROOT内，字节与v2完全相同（SHA d009cd6b06b1a429b6c67429c6d4da4c8ea9c4bc0e5f50a81cab237e1d54f8e9）。R378 --basetemp放在repo内，旧test使用tmp_path却假定它在repo外。loader只要求root内普通无symlink、expectedSHA及sources匹配，不限制原文件名；该正例输入被接受符合现有产品合同。

两目标module其他tmp_path用途是改源副本或显式symlink，不依赖仓库外假设；没有理由扩修。

## 最小改动

仅tests/test_marker_association.py中该param分支和必要stdlib import/cleanup上下文：在canonical /tmp创建唯一TemporaryDirectory，写同字节registry，保持到loader调用后finally/context清理。显式assert文件普通、无symlink祖先、not altered.resolve().is_relative_to(ROOT.resolve())。保留原共享同字节断言、pytest.raises(ValueError,match="registry")、CONFIG_SHA256/root=ROOT及parent_link/file_link原两负例。

可用ExitStack托管该分支；不得改loader白名单/源绑定、弱化raises、加skip、伪造错误或整体迁出basetemp回避问题。v1/v2、6sources、STATIC/INITIALframes和assets全冻结，DEVELOPMENT_ONLY/NOT_ADMITTED保持。

## 运行与预算

R378 pose_evidence_asset_guards仍用原一次180秒，独立完成；其新失败不在此范围。等其终态/cleanup后复核输入，再改唯一test文件。现有实际失败直接作为RED，不重跑RED/不加focused或collect-only。

新R391完整两module只跑一次，child≤300秒、cleanup≤15秒、总墙钟≤600秒、0retry/0parallel，预期52PASS且无skip。继续把新basetemp放repo内以真实验证外部fixture独立于pytest临时根。原R378预算与失败不重置，未变poseguard不重跑。

当前workspace-write/networkrestricted/.gitreadonly，/tmp为可写ROOT外路径，不能继承browser升级权限。外部目录实际创建失败则保留环境证据并停止，不回退ROOT内或改断言。记录完整JUnit/log/结果、源和资产前后hash与ownedcleanup；独立审查后写阶段总结。

## 后续与验收

R379原独立asset工作在R378/R391终态清理及审查移交后继续，先核其原27pins；原命令/预算/交付边界不变。R377的19未满足目标仍开放，marker通过不代替browser通过。

验收是输入位置真的ROOT外、原拒绝断言成立、52项完整通过及冻结源/帧/资产不变。仅软件测试与development注册，不是产品loader漏洞修复、真实效果或正式研究验收。

完整原始失败、输入SHA256、原50pins审计、新精确argv/env与停止门见plan.json。规划没有产品导入/测试/Git/网络/signals；仅一次搜索猜测文件名不存在，已按实际import找到marker_association.py，无源码修改。
