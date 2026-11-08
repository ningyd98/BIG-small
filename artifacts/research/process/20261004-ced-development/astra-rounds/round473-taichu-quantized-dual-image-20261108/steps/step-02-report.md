# 阶段 02：隔离运行环境

PASS_ROUTE_B。A 因永久浮点解压排除；B64包闭包锁定安装，R481 追加4个缺少依赖，最终pip check rc0。

命令入口：`preflight_runtime.py b; isolated pip check`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/runtime-a-execution-gate.json`，SHA256 `5250f3cab02ef7a37230adf66fcccb082379910a775e26b2912eed57aaaa4d80`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/runtime-b-preflight.json`，SHA256 `a0173daf8b4bf52916b41f5c5cc094b56edf81eee81009b0b73895d5c6da10b0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/dependency-verification.json`，SHA256 `17c34bc6a2c23c40f9d0506def31eac2bf9a5a4f19981b6937235a3e033ebbe0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/final-pip-check.stdout`，SHA256 `9261363b733079a641c2e4cc9bc46ffa1d8336945a87f807b6cf68847dbc9b09`。
