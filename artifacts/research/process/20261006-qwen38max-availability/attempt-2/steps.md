# TTY 修复步骤

原错误和原脚本保持冻结；实施前全部输入哈希复核通过。真实 TTY 前置验证 PASS，唯一一行替换记录于 implementation.json；相同 read_key 诊断由 tty-red.json 的 FAIL 转为 tty-green.json 的 PASS，ECHO 关闭和完整终端状态恢复均验证。

新离线检查 PASS，旧 offline-check.json 保留。真实隐藏输入成功，后续 GET/POST 两次请求均 HTTP 200，无重试。云端严格文本输出为 OK.，与只要求 OK 的提示有句点差异，按原计划单独记录，不修复/重试。

开发验证、真实 API 可用性与正式研究验收分别记录；本轮正式研究验收未测试。
