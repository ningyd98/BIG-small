# R217 — writer 新增块纯搬移计划

实际作者 gpt-6-astra。状态：等待 ROOT 门控；唯一实施者为原 /root/p6_stage_b_sol（gpt-6.1-sol）。

原 native patch 返回 {}，d598f7 元数据 exit0 发现 required227116_prefix_equal=false，old168003_prefix_equal=true。重复 assert 锚点把 writer 全块插入旧五节点之间。这是源码位置约束违例，不是测试失败；原 patch、false 结果与当前完整快照均保留。

独立按原 patch 的全部新增行提取377行/25584B完整块（SHA e941826191fa6e303163d93ecbda6081b1d2fac56dd22a11bfa5594851785b2b）。真实起点212907含两个LF，def起点212909不是搬移边界。已逐字确认 current=old[:212907]+block+old[212907:]，删除整块即恢复227116B旧文件；两侧皆全行边界。

只允许同一Sol在 ROOT fullread/pin gate后，把该块原字节移至旧227116B EOF：after=old+block。预期仍252700B，SHA d0509a55284970095db4cdba5a21ba79e4a3235978aa7d63a67b064333562bf3。禁止切碎 def、重格式化、修改helper/body/断言/节点、修其他语义。写前再次CAS当前完整SHA并独占保存physical before；允许仅此确定字节重排的stdlib写入。

作者新存 implementation/before-test.py、after-test.py、limited.diff、change-report.json及实际回执；原R204/R217原件不动。ROOT随后全文读377行writer块并核精确纯搬移、227116全前缀/168003旧前缀、runner/角色、19产品与211保护连续性，才恢复原R204最终准备。当前块语义尚未审定、未运行，不因纯搬移宣称fixture可用。

完整10输入pins、精确等式及门禁在 plan.json。两T2槽仍0/1 HELD；新增执行/测试/静态/审查/Git槽0，无重置。仅正常stdlib字节/hash/diff范围核对，不运行产品或AST/import/compile/probe/SQL。任意新差异/失败STOP下一Astra；T2/T12/native/formal均不晋升。计划保存后STOP，不由规划者实施。

