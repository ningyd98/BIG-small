# 固定工具链准备

原环境没有 Go。首次按[Go 官方下载清单](https://go.dev/dl/?mode=json)选定 go1.27.1/linux-amd64，180秒下载超时（exit28）；原命令日志与失败[记录](report.json)保留，未运行或安装不完整包。

改用本机APT清单的固定 Ubuntu `golang-1.22-go` 和 `golang-1.22-src` 版本 `1.22.2-2ubuntu0.4`。两包分别25,920,686字节和19,730,376字节，均与清单SHA256和大小匹配，解压于 `/tmp/bigsmall-native-clock-ubuntu-go1.22.2/sdk`；没有向系统目录安装包。`go version` 返回 `go1.22.2 linux/amd64`，exit0。可执行文件SHA256为 `89b81bd72c27404ccfd701c136b7e3ace9a4ccb26d96d97e874b48829aed27a1`，详情见[成功记录](ubuntu-toolchain-report.json)。

后续构建显式指定此 Go 路径、GOROOT 和 GOTOOLCHAIN=local，避免自动下载或切换工具链。大包位于/tmp，Git仅保存清单、日志与精确哈希。本次只是工具链准备，没有编译Roughtime wrapper，没有签名原包、时钟UDP查询、模型、相机或物理调用；不授予UTC校准、原生来源或正式验收权限。
