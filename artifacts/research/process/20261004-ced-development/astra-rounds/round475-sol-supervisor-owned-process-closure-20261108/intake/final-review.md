# R469 一次独立静态审查原始结论

来源：`/root/r469_runner_review`，Critical 0 / Important 4 / Minor 0。当前 runner 不宜执行，需下一轮实际 Astra 处理监督与收据边界。

1. **Important** `run_nominal.py:682-685,563-565`：Worker is reaped before post-exit discovery of adopted descendants; cleanup covers known identities only. A child born between samples can survive unnoticed. Python audit hook is not proof about native forks. Plan explicitly names stat/statm only, whereas runner also reads own task/children; next plan must explicitly authorize narrowly scoped own/adopted PID metadata.

2. **Important** `run_nominal.py:780-789`：compliant ignores available wait4 and worker self maximum RSS. A measured peak above4GiB at exit can be labelled compliant if missed by parent samples.

3. **Important** `run_nominal.py:743,756`：Blocking wait4 and subsequent seal are not supervised by960s outer budget; outer_960s_compliant is only retrospective. Resolve honest unkillable/unreaped ownership vs lock lifetime without claiming hard closure or releasing while descendants live.

4. **Important** `run_nominal.py:335-352,496-498`：operation_counts uses only journal CAPTURE BEGIN. Backend catches observer failure and keeps foreground operations, so lost BEGIN plus successful END or loss of both can yield false render_exact0. Production operation_ledger must contribute loss-aware denominator/unknown intervals. Qualification currently rejects failures, but failure evidence remains inaccurate.

生产接口未发现静态签名错误；原 attempt 先保存后判门、隐藏TTY及异常文字抑制符合计划。

Static-only; no modification, runner/preflight/tests/services/API/render/physics/credentials/other-process content.
