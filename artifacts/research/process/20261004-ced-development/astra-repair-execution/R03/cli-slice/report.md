# R03 有界命令行 slice

QUIET，等整体R03软件独审。本slice只新增CLI/tests，未改publication/reset modules、config、worker或旧原件。按既定接口，默认只调用validate_startup_inputs_v2，输出INPUTS_ONLY/NOT_RUN；不创建output/app/repo/job/lease/backend/network。显式--execute-once只调用一次真实startup factory和app.execute_once；保存完整receipt，只有prefix_complete严格为True才退出0，否则退出1，native UTC仍UNAVAILABLE。失败不重试或删partial原件。

缺CLI的单项RED已保留，后续9项CPU通过（0.43s）；包括默认无effect、原路径传递、真完成和四种非True状态、失败保留、缺argument先拒绝。Ruff/format通过，两源内存compile通过；MYPYPATH=src、follow-imports=silent的owned CLI mypy通过（1源），不声明整体模块静态已通过。初次格式检查失败和初次缺MYPYPATH的import-untyped日志保留，均未作为行为缺陷。

全部测试为CPU monkeypatch effects，真实app/lease/UDP/model/renderer/physics/provider/hardware均0；默认真实policy校验和实际CLI执行尚未运行。源码/测试及各命令原日志SHA见report.json。根审查与计划已有全部研发授权，不另请求许可；独审R03全source闭包后由root唯一实测。Git未stage/commit本slice。
