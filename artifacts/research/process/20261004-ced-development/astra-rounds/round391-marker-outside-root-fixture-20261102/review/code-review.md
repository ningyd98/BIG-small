# R378 / R391 联合独立代码审查

结论：`APPROVED_R378_R391_DEVELOPMENT_SCOPE`；可释放source writer给R379，须先核其原27pins和即时前置。Critical/Important/Minor均无。HEAD `fdb2e94d3d7bc041e7d958f2514a08406fad4668`；本席未导入产品、运行测试/网络/信号或Git写，只新建review报告。

## 代码与计划对照

v2字节等于v1只替换registration_id和已审marker_association来源SHA；新配置SHA固定为d009cd6…，六项绑定集合和其余五项、几何/资产均不变。两消费者改用v2和字面量预期SHA；两个新增guard覆盖旧v1仍拒绝、v2精确两处差异、实际loader成功与交叉SHA拒绝。原函数的断言除计划允许的literal SHA替换与路径负例修复外均精确保持。

R391相对其冻结输入只变stdlib imports和outside_root所属函数。canonical `/tmp` 的TemporaryDirectory由ExitStack托管至loader调用后；普通文件、无symlink祖先、实际ROOT外均显式断言。原同字节比较、registry ValueError、CONFIG_SHA256/root=ROOT和parent_link/file_link逻辑保留，未动loader。初次失败是持久basetemp位于ROOT内导致负例假设不成立，不能称产品loader漏洞。

## 已核对终态原件

| 轮次/阶段 | 结果 | 证据边界 |
| --- | --- | --- |
| R378首次完整marker | 51PASS/1FAIL，17.226秒 | outside_root DID NOT RAISE原件保留，未重跑RED |
| R378独立pose/evidence/asset | 23PASS，1.851秒 | 原模块完整通过，R391未重复执行 |
| R391完整marker | 52PASS，17.822秒 | 与初次相同52个case身份/顺序，0skip/failure/error |

最终52+23共75个不同必需case。三阶段各1092条source记录前后相同，source_drift/errors/remaining_live空、reaped=true；argv/env及实际spec SHA匹配。50/26计划输入均复核，仅各轮允许的测试改动有差异；v1、v2、六sources及帧/资产冻结值维持。完整pins/用例/原件SHA见JSON。

## 验收边界与交接

静态/初始历史帧只到OBSERVED_CANDIDATE/DEVELOPMENT_REPLAY，保持DEVELOPMENT_ONLY、NOT_ADMITTED、whole identity UNKNOWN、extent_complete=false、界限None和stability UNKNOWN；旧时间、来源、标定和原帧均未重写。没有新相机采集、物理/native/full-extent或正式研究验收升级。

R377的19个browser开放case仍存在；R390 URI静态问题已交实际AstraR392且script未运行，不阻塞独立asset。R379按自己的原计划和实际权限串行继续，不能继承browser升级权限。完整checkpoint、受保护temporal/历史gitlinks、后续asset实现和真实效果不在本席判断范围。精选Git交付由协调席完成，本审查无提交/推送声明。
