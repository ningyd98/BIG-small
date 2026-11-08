# R504 — 同算法 CPU gate 一次续跑

实际规划模型：gpt-6-astra；仅规划。完整输入SHA/bytes见plan.json。

已核原launcher：timeout=true、9.0695秒、rc=null、无最终报告，属于阶段剩余时间截断，不能称backend不兼容，也不能称完整gate通过。批准一次完全相同算法的新唯一输出续跑，当前仍0load/gen。

复核输入SHA和原子进程退出；复制新cpu_contract_r504.py仅更改输出名并补R503已要求的证据：原/测试BPE副本序列化hash与diff严格仅normalizer，原tokenizer/adapter不变；每个fixture两流完整IDs、精确序列化hash、拒绝位置、原字节/NFC差异，27ASCII见证完整记录。不得删测试、改变oracle/接受条件或修改adapter/fixture。所有文件新命名，旧r503缺失报告记超时未产生，不伪造补写。

原21项、27见证、词表/D28/187例外、三EOS、1030前缀/视觉、状态隔离、72包和codec/硬件门槛全继承。完整新PASS后独立核报告与证据文件SHA才准A；单次最多120秒，未知语义失败为最终负结果，超时为INCOMPLETE_TIME，无再次续跑或改方法授权。

总 **16:19:20 UTC** 硬截止不变；本次CPU最晚 **15:59:00**，A **16:03:00**，条件B **16:09:00**，保留末10分钟报告/Git。最大1load/24gen、每请求180秒、无warmup不变。B必须真实A格式4/4、来源专项计划及时间预测全部满足，否则NOT_RUN；resident最多等5分钟，不再加载。全部历史失败与本轮结果分层报告、显式artifact交付并核三SHA，保护共享状态。
