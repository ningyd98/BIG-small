# R379 独立代码审查

`APPROVED_R379_SOFTWARE_ASSET_SCOPE`；Critical/Important/Minor均无。可交付本轮manifest/doc/test及精选证据。HEAD `fdb2e94d3d7bc041e7d958f2514a08406fad4668`；本席仅只读核对、写新review，没有测试/产品导入/网络/信号/Git写。

manifest与HEAD精确只有旧6a→当前66 SHA及v2→v3两值变化。27计划输入已逐项核对，仅允许三条源路径有差异；当前scene和三个marker XML字节保持，历史4个Git对象与归档逐字相等。文档准确说明项目参考模型、历史版本和旧数据身份，不将登记版本视为官方几何或物理验收。

原Registry正例的AST语句完整保留，新增v3/精确场景路径断言。两个真实Registry负例分别使用旧hash+当前模型、当前hash+隔离篡改模型，均要求真实hash mismatch；仓库模型不改、无mock/hash替代。

| 阶段 | 结果 |
| --- | --- |
| asset_registry_green | 3PASS，0.634秒，0skip/failure/error |
| mjcf_load_reset_step | 3PASS，1.240秒，0skip/failure/error |

原MuJoCo两文件与HEAD逐字一致，真实当前场景load/S01reset/simtime0/七关节、80step时间与状态推进、160step FK变化断言均执行。两stage各1074条source记录前后同，source_drift/errors/remaining_live空、reaped=true，argv/env与实际specSHA相符。

结论限于软件仿真资产登记与CI；R377browser19case仍开放，没有抓取任务/真实硬件/官方Franka/新标定/正式研究验收升级。R390尚未执行诊断；根因不在本报告判定。Git提交/推送/三SHA核验由协调席按原门完成，本席无该类成功声明。
