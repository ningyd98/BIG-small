# R272 — pytest ini 类型归一化

实际 `/root/astra_status_plan` / `gpt-6-astra`；仅计划，未修源或运行。

冻结候选19905B/f7585469…在pytest_configure把getini原值直接与整数540比较。已安装pytest的 `_get_override_ini_value` 1714–1729返回 `-o` 拆分后的字符串；`_getini` 1690–1691在未指定类型时原样返回。原faulthandler注册未指定type，其71–72行显式float转换。故这是静态候选类型缺陷，不是已运行测试失败。

唯一允许变化：
```python
configured_timeout = float(config.getini("faulthandler_timeout") or 0.0)
```
保留后续 `configured_timeout != 540`、原异常流和所有其他字节。采用native同一归一化；不增加540默认、容差、clamp或时限，不新增字段/import/helper。

原候选和native原件不覆盖。唯一Sol先保存完整before/manifest/base64，再在R272独占保存新候选/limited.diff/report，最后向尚不存在的R268实际plugin路径native Add。ROOT按完整源码/native重建、精确单行替换和实际输入SHA核验；原runner不需修改。全部14输入完整pin及派生expected bytes/SHA在观察中，派生值不是已落盘候选。

R268/R269原计划、测试、产品、observer、上下文、角色与两次诊断预算不变；当前STATE/PHASE仅按R268 context manifest精确代际解析。本轮新增执行/测试/静态/SQL/Git/验证流水线0。runtime仍需ROOT完整source/native/input/argv/role门。冻结后STOP。
