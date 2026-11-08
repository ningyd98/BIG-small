# 阶段 03：同步双图及完整 processor

PASS。S01 seed0 320x240同一静态状态；RGB先、depth后，两张不同图实际processor输入。

命令入口：`capture_pair.py; process_pair.py b-r481`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/dual-image-protocol.json`，SHA256 `359361fb23e550da6d94083895873543a892911e60fa0cad5fd620c772d80356`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/processor-b-r481.json`，SHA256 `be83b6994d84831adbbffed30c945755eba43e1f338fdd848139917649996dc9`。
