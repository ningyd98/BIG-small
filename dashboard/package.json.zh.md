# package.json 说明

该 JSON 文件声明 Dashboard 前端的 npm 脚本、运行依赖和开发依赖，是本地控制台构建、测试、OpenAPI 类型生成和 Playwright 验证的入口配置。

该文件不保存 API key、token、控制器地址或真实硬件配置；需要变更依赖或脚本时应同步检查 `package-lock.json`、CI 前端任务和 `scripts/README.md` 中的启动说明。
