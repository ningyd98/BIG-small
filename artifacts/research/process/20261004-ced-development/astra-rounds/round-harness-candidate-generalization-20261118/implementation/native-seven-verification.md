# 七例真实模型归档复算回执

2026-11-18。原验证器以候选 `3ca2f6415b330d38ddc2d834c5f788a56c0d9517` 的 `src` 优先导入，导入日志确认 `harness.evidence` 和 `simulation.mujoco.episode_evaluator` 均来自候选目录。清除渲染环境变量，以 CPU 执行。输出为新建 `/tmp/bigsmall-native-seven-20261118.3btMaPHP/native-verification.json`。

```bash
set -euo pipefail
cd '/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118'
old='/home/ningyd/.codex/worktrees/v4-marker-ambiguity/BIGsmall/experiments/results/phase9/real-harness-20261118'
audit_dir=$(mktemp -d /tmp/bigsmall-native-seven-20261118.XXXXXXXX)
unset MUJOCO_GL PYOPENGL_PLATFORM DISPLAY WAYLAND_DISPLAY
export PYTHONPATH="$PWD/src" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export CUDA_VISIBLE_DEVICES=-1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
python_bin='/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python'
history='artifacts/research/process/20261118-real-model-harness'
nice -n 10 "$python_bin" -s "$history/verify_native.py" --raw-root "$old" \
  --output "$audit_dir/native-verification.json" 2>&1 | tee "$audit_dir/verify-native.log"
diff -u "$history/native-verification.json" "$audit_dir/native-verification.json" \
  | tee "$audit_dir/native-verification.diff"
cmp "$history/native-verification.json" "$audit_dir/native-verification.json"
sha256sum "$history/verify_native.py" "$history/native-verification.json" \
  "$audit_dir/native-verification.json" "$audit_dir/native-verification.diff"
```

验证器退出 0，输出 `{"verified_rows": 7, "component_completed_count": 3, "physical_success_count": 4}`。1181 行 `diff -u` 为空，`cmp` 退出 0。原始账单未知。固定场景修后 2/2 完成，保留原失败后 2/3。新 seed 1/4 完成、2/4 独立物理成功。七例历史调用为 6 云请求、26 本地生成。本次是候选软件对原记录的只读复算，实际模型加载、生成、云请求和硬件调用均为 0。

| 文件 | SHA256 |
| --- | --- |
| 归档输出及候选复算输出 | `3cb180a2d995c2c0d2664347d34daf7150ad2242f3669f42fbc4057c4ad643d5` |
| 原七例验证器 | `259fb003b6f30a59bdb477ab46daf12a7056ff873feba9f5a7646caf7897637a` |
| 旧 worker 验证器 | `8d3664b60f85ffb9a3e6014d021b646c6e851b58546ca99b37e1c599f4ec293f` |
| 候选 `harness/evidence.py` | `2ab6602c564e4633068303f623a84be8968b96bd1f954518493727949fb3ab5b` |
| 候选 `simulation/mujoco/episode_evaluator.py` | `a0b5891a70752400dcf0dea0cbe837476114148000b9eb345c27fe468860af50` |
| `verify-native.log` | `b85da00c3981f3800bc091d97fc97ce572927eb0b177a17330e2cb1ec51fcab5` |
| `imports.log` | `d32abdb43dbab76e70405d5a0ef798aef875b1620b4f70182dd1648ad4a8d40f` |
| 空 `native-verification.diff` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

原七例各自的实际来源由原验证器绑定。`fixed-01` 使用 `318a546dd3a945bddc076cc06bc3528966a4051a`，`fixed-02`、`fixed-03` 和 `varied-44101` 使用 `pre-camera-binding`，`varied-44102` 至 `varied-44104` 使用 `post-camera-binding`。`varied-44103` 的独立物理成功和 worker 失败同时保留。正式研究 `NOT_ACCEPTED`，新动作资格组 0，实机 `NOT_STARTED`。逐例数值见[七例原读出](../../../../20261118-real-model-harness/native-verification.json)。
