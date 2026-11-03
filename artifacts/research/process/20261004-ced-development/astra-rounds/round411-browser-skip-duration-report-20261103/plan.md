# R411：报告可选耗时与输出父目录前置

实际 gpt-6-astra；UTC 2026-11-03T09:04:09.373670+00:00。两项均为纯报告I/O错误：原E2E06有skipped无time，直接索引抛KeyError；R410/preflight未创建导致报告写入FileNotFoundError。原工具失败保留，未冒称完整内联脚本已冻结。真实测试/源码/清理无影响。

仅派生报告补正：缺time保留null及duration_available=false，仍SKIPPED；原XML分类核验默认39P1S、research3P、共43/42P1S，old19按classname+name唯一真实匹配。20份冻结research输入实际包含backend.py与19fixture，按原stage相对路径核验，不假设全在fixture子目录。

允许已声明报告父目录mkdir(parents=True,exist_ok=True)，包括R410/preflight；新文件x排他写，已有文件绝不覆写。R410内容/source/rawcleanup及SQL门仍须独立复核后才写browser-terminal，创建目录不替代门。R408 step-report仅追加。

一次≤60s纯静态报告/校验，不跑测试/产品import/SQL/network/Git，不改XML/源码/旧计划。R410合法格式化可独立进行，浏览器报告只认执行时冻结字节/hash，不假定报告生成时当前源码仍旧SHA。最终独审/精选交付另计划，无helper审查链。
