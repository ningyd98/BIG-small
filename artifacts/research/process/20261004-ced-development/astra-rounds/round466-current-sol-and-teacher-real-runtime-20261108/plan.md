# R466：真实运行前 GPU 观察边界诊断计划

实际规划模型：`gpt-6-astra`；状态：`PLAN_FROZEN_NOT_EXECUTED`。本计划只释放一次主机上下文只读诊断，不释放 P1/P2 工作负载。用户“开始真实运行”的授权已具备，无需新增确认循环；工具自身自动审批仍适用。

## 问题与证据

默认受限 exec 的 GPU memory 和 compute-apps 两条 `nvidia-smi` 查询均 rc9、stderr 空，原始 stdout 均为：

> NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. Make sure that the latest NVIDIA driver is installed and running.

原始命令、145 字节 stdout、空 stderr 保持在 `intake/`。磁盘快照 free 488838402048 字节；P0 基线 `ae3b88370276ebe0b2782720588c0b52d6c8e1d8`。旧 R450 记录的是当时 Qwen 已停止，不能代替当前检查。

H1：受限环境阻断设备/驱动访问；H2：主机驱动/设备实际不可用。当前均未确认。主机成功仅支持观察依赖执行上下文，不足以确认具体 sandbox 机制。

## 输入冻结

`plan.json.inputs` 保存本计划直接输入的路径、字节数及 SHA256；`intake/input-pins.json` 引用既有 R461/R465/R450 原件，不批量复制。规划时 11 项原 pins 均匹配。ROOT 实施前重新核对每一项及基线、产品和阶段树。任何变化先复核适用性，相关变化未解释不得执行。

## 限定执行

ROOT 将下列完整命令以 **一次** `exec_command(sandbox_permissions="require_escalated")` 执行。两条 nvidia-smi 各一次、既有 Qwen user unit show 一次，各 8 秒；整体 45 秒，TERM 后 2 秒收尾，retry0。设备仅 stat，驱动仅两条公开版本元数据，进程仅本次 compute 返回 PID 的 UID/状态/cgroup/comm（最多32）。不读取 env、cmdline、凭据、运行 DB。命令不写文件；ROOT 保存新的外层 stdout/stderr/rc/context/UTC，并将 base64 原始字节解码到全新证据目录，不覆盖 intake。

```bash
/usr/bin/timeout --signal=TERM --kill-after=2s 45s /usr/bin/python3 - <<'GPU_DIAG'
import base64, csv, datetime, glob, io, json, os, stat, subprocess
from pathlib import Path
out = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "scope": "host_read_only_gpu_diagnostic", "commands": [], "metadata": []}
commands = [
    ("gpu", ["/usr/bin/nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"]),
    ("compute", ["/usr/bin/nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"]),
    ("qwen_service", ["/usr/bin/systemctl", "--user", "show", "qwen38-flash-strata.service", "--no-pager", "--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID,ControlGroup,NRestarts"]),
]
for label, argv in commands:
    row = {"label": label, "argv": argv}
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8, check=False)
        row.update(returncode=p.returncode, stdout_b64=base64.b64encode(p.stdout).decode(), stderr_b64=base64.b64encode(p.stderr).decode(), stdout=p.stdout.decode("utf-8", "replace"), stderr=p.stderr.decode("utf-8", "replace"))
    except subprocess.TimeoutExpired as e:
        row.update(returncode=None, error="TIMEOUT", stdout_b64=base64.b64encode(e.stdout or b"").decode(), stderr_b64=base64.b64encode(e.stderr or b"").decode())
    except OSError as e:
        row.update(returncode=None, error=str(e))
    out["commands"].append(row)
    print(json.dumps({"command": row}, ensure_ascii=False), flush=True)
for name in sorted(glob.glob("/dev/nvidia*")):
    try:
        s = os.stat(name)
        out["metadata"].append({"path": name, "mode": stat.filemode(s.st_mode), "uid": s.st_uid, "gid": s.st_gid, "rdev": s.st_rdev})
    except OSError as e:
        out["metadata"].append({"path": name, "error": str(e)})
for name in ["/proc/driver/nvidia/version", "/sys/module/nvidia/version"]:
    try:
        with open(name, "rb") as f:
            data = f.read(4097)
        out["metadata"].append({"path": name, "text": data[:4096].decode("utf-8", "replace"), "truncated": len(data)>4096})
    except OSError as e:
        out["metadata"].append({"path": name, "error": str(e)})
compute = out["commands"][1]
if compute.get("returncode") == 0:
    pids = sorted({int(row[0].strip()) for row in csv.reader(io.StringIO(compute.get("stdout", ""))) if row and row[0].strip().isdigit()})
    out["compute_pid_count"] = len(pids)
    out["ownership_complete"] = len(pids) <= 32
    for pid in pids[:32]:
        row = {"pid": pid}
        for filename in ["status", "cgroup", "comm"]:
            try:
                text = Path(f"/proc/{pid}/{filename}").read_text()[:8192]
                if filename == "status":
                    text = "\n".join(line for line in text.splitlines() if line.startswith(("Name:", "State:", "PPid:", "Uid:", "Gid:")))
                row[filename] = text
            except OSError as e:
                row[filename + "_error"] = str(e)
        out["metadata"].append(row)
print(json.dumps({"result": out}, ensure_ascii=False), flush=True)
GPU_DIAG
```

## 判定及停止边界

- 两个 GPU 查询 rc0 且内存值可解析、GPU 非空，才记 `HOST_OBSERVATION_AVAILABLE`；原 rc9 仍为原失败。
- compute 为空，既有 Qwen unit loaded/inactive/dead 且 MainPID/ControlPID=0，内存与所有权无矛盾，才记 `RESOURCE_CLEAR_AT_SNAPSHOT`。不作未来独占预约，不凭此声称工作负载显存足够。
- 发现占用或服务活跃记 `RESOURCE_BUSY`，只保存身份/状态，不停止或杀进程。
- 主机仍失败、超时、审批拒绝、状态缺失/无效或所有权不完整记 `UNRESOLVED`。本轮额度耗尽，受影响工作暂停；任何进一步修复或重试先由实际 Astra 新轮规划。
- 禁止 reboot、安装驱动/包、变更内核模块、服务启停/重启、启动模型/renderer/engine/API。禁止修改产品、测试、R461/R465 和历史失败；不新增软件测试或实际资源额度。

## ROOT 步骤与报告

S0 核对 pins、基线与无并发启动，保存计划 SHA 和精确命令。S1 唯一诊断并保存新原件。S2 将受限 rc9 与主机结果并列，分别记录观察权限、memory、compute 所有权、Qwen 当前停止状态。S3 写 `implementation/step-report.md` 与 `.json`，包含时间、命令/输出 SHA、实际返回码、执行次数、偏差和边界，并汇入阶段总结。S4 资源允许时，再由实际 Astra 冻结 P1/P2 新 source generation、精确 runner、计数及预算；P1/P2 独立，GPU 阶段串行。

验收仅限资源观察证据。API/physics/render/service mutation/model startup 全0；full NOT_RUN，native UNKNOWN，formal NOT_ACCEPTED。规划期间 `python` 别名不存在返回127，仅影响只读 intake 展示；未修环境，已选择现有 `python3` 并固定诊断解释器，详情与原输出保存在 JSON 规划注记。
