# openapi.json 说明

该 JSON 文件由 `scripts/export_dashboard_openapi.py` 和 `npm run api:generate` 生成，用于前端从真实 FastAPI OpenAPI schema 派生类型。

它是生成产物，不应手工编辑；需要变更接口时应修改后端路由或 Pydantic schema，然后重新运行 API 生成流程。该文件只描述 Dashboard 和仿真/模型控制 API，不保存密钥、token 或真实硬件连接配置。
