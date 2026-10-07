# OC1 isolated test receipt output Implementation Plan

> **For agentic workers:** Preserve root's existing execution arrangement. Two execution items only. The planning dispatch writes only this plan; the eventual complete-suite run belongs to the new root review evidence.

**Goal:** 隔离现有真实Linux CPU factory测试的receipt输出，使完整pytest可重跑且不覆盖冻结原件。

**Architecture:** 仅修改tests/test_operational_time_v1.py现有单个测试的tmp_path fixture参数和artifact赋值；生产源不变。一次最终完整60用例验证同时供root独审，日志/新CPU receipt全部落新review目录。

**Tech Stack:** 现有pytest tmp_path、pathlib.Path、stdlib AST/哈希及Ruff；无新依赖、无工厂参数或CLI扩展。

**Spec:** 根AGENTS.md保留历史原件；原OC1计划的独审重跑要求；round58静态修复的41份implementation冻结证据及静态档案。输入和完整保护清单固定于plan.json。

## Global Constraints / Review Focus

- 唯一代码修改文件为tests/test_operational_time_v1.py；生产src/cloud_edge_robot_arm/research/operational_time_v1.py必须保持SHA b1fa45a96837072d7bcf8cec57d1a7ae01dceeabec0131503b6aee5ab27dd90b、20734 bytes。
- 测试before SHA a339a80f8ac6a4b8eed1ac363046b148203930a4f5a2999779d58d7bdc002038、24350 bytes。函数名字/参数化集合及唯一60分母保持；仅多一个pytest提供的tmp_path参数。
- CPU receipt字段、真实零参数factory、所有断言、拒绝语义、计数/TTL/deadline/causality不变。不能mock最终verdict、改__file__或动态换加载路径绕过审计。
- 不采取“备份旧证据→覆盖→还原”；原41文件、static-fix原before/after/report/logs和原real-startup-cpu.json在全程仅只读。新receipt只从新tmp目录复制到新review目录。
- 不network/model/physics/renderer/camera/decoder/hardware/实际任务，不改rootdocs/Stage/Git/配置。真实Linux CPU读取与物理actual=0分别记账。
- 线程ID复用目前无本轮失败证据，不扩大为生产生命周期改造。该工厂仍只供SOFTWARE计数能力，不授予worker/lease/native。

## 原失败证据、根因与风险

这是静态证实的覆写风险，尚未通过破坏性重跑触发。当前测试第559行无fixture参数，第560—563行artifact固定到仓库implementation/logs/real-startup-cpu.json；第568行SUPPORT_UNAVAILABLE分支和第608行成功分支均调用artifact.write_text。原CPU文件SHA e5030d84836af43fc79b9a93a356b32f8b567bfa5413c4ad4445bff9fa05fbb5、1721 bytes；该文件在静态修复保护的41项内。

root尚未重跑完整60；round58只跑两copy/pickle用例，所以原CPU文件仍与冻结清单一致。本次已只读核验41项及static-fix全文件SHA。原60pass、round58两项pass及静态通过均保留其历史版本含义，不重写原报告来隐藏此风险。

根因是测试证据目的地未隔离。pytest tmp_path提供用例本地新目录，成功和失败分支共享新artifact赋值即可消除固定原件路径；不需要改source或增加测试用例。修改后CPU行为应完全等价，仅receipt输出位置按本轮要求改变。

## 执行项（最多两项）

- [ ] **1. 冻结当前测试并做最小fixture修正。** 实施前核对plan.json required输入及保护清单，确认现有生产源SHA不变。在新astra-repair-execution/OC1/test-output-fix/before/tests/test_operational_time_v1.py保存当前测试字节供diff；不得改旧static-fix快照。仅把函数签名改为test_real_linux_startup_factory_cpu_only(tmp_path: Path) -> None，并将artifact赋值替换为tmp_path / "real-startup-cpu.json"。原Path import已经存在，不新加依赖；其余write_text参数、exception分支、factory调用、断言和payload不变。用stdlib AST精确比较：将修改后该函数新增的唯一tmp_path:Path参数及首个artifact赋值还原成before节点，再比较全测试AST相等；其他所有测试AST、名字/参数化/断言不变。静态扫描本测试仅两处artifact.write_text均解析至tmp_path变量，去除仓库固定输出常量，无其他写路径；同时保存原风险节点/行号和最小diff作为原失败证据。Ruff check --no-cache及ruff format --check --no-cache只查该测试文件；source仅SHA quiet，不重跑source mypy。任何新失败或超出这两处修改先Astra下一轮。

- [ ] **2. root一次最终完整60验证兼独审，所有证据新目录。** root在修正后test/source固定SHA上独审最小diff与AST结果，使用新且不存在的astra-repair-execution/OC1/independent-review-round59/作为报告目录；stdlib tempfile.mkdtemp在/tmp创建唯一父目录，并选其尚不存在的pytest子目录为basetemp。不得把旧artifact目录用作basetemp，也不得复用pytest会清空的旧目录。运行前记录并确认plan.json的41项implementation和全部static-fix文件SHA/bytes，同时记录source及新test。随后只运行一次完整文件：PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=<新绝对路径>/pytest tests/test_operational_time_v1.py。不改测试输出相关环境，不特殊monkeypatch factory/output；pytest原生tmp_path完成隔离。无论退出码，立即在finally只读重算同一保护清单及source/test，全部必须不变；结果/命令/stdout/stderr/exit保存新review目录。期望60 passed、0 failed、0 skipped，原60与此60仍同一唯一分母，不累计120。枚举该新basetemp内real-startup-cpu.json，去除pytest current符号链接别名后应有一个真实新文件，解析其状态与原测试相同schema/字段；值属于本次真实CPU读取，不要求与历史counter/PID相等。只复制它到新review目录real-startup-cpu.json并登记两端SHA；绝不回写implementation。如果工厂真实不支持，保留tmp下SUPPORT_UNAVAILABLE与失败，不skip伪称通过。root原已计划的独立public API计数反例在同一新review目录留证：现有私有raw-source seam只控制原始读数/身份，调用真实owner公开event/current/age/deadline方法，不mock verdict，覆盖合法重叠、5秒+1ns、deadline等值、foreign/copied；不增加pytest套件分母或改production。本项完整60供修复验证及独审共用，实施agent不先重复跑60。最终report.md/json、pins-before-after.json、AST/diff/静态结果及新receipt全部新建，旧报告不变。保护SHA漂移或新问题立即停止并保全现场，不恢复旧文件掩盖，交Astra下一轮。

## 验收与实际运行前置

修复最高PASS_SCOPED_TEST_OUTPUT_ISOLATION；root完成原OC1独审后自行决定限定SOFTWARE结论。默认完整该pytest文件在新basetemp运行、原保护SHA前后全同、新receipt位于tmp并可独立复制，是有意义的实际验证，不以仅文本replace或备份还原证明不覆写。失败分支同一新artifact变量由精确AST证据覆盖，本轮不人为造新工厂故障以再跑一套。

新一轮真实factory CPU读取需如实记录；不产生物理/模型actual、未来H_D、SI/UTC精度或worker授权。OC2/3/4与真实restart/suspend/hostpause前置继续未完成，不运行任何实际任务来验本修正。

本次规划只读源码、原CPU receipt、41保护项与静态报告/档案，未运行pytest/static或项目module。仅新增本目录plan.md/json，未写源码、旧原件、rootdocs或Git。Astra角色来自用户指定派单，运行时模型身份未独立探测。自查覆盖单文件上限、两个允许AST变化、成功/失败分支输出、默认完整验证、原件保护和不重复分母。
