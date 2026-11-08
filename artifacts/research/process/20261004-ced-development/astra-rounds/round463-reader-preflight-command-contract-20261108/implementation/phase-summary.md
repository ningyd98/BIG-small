# R463 命令契约步骤报告

实际 Astra 计划已读并核对 pins；R461 原输入 31/31 匹配。后续 Python 使用 `.venv/bin/python`，runner 从冻结 pins 中的 R458 实际路径复制并核对原 SHA256，其他文件按 rg 发现结果读取。未安装依赖或调整 PATH/服务。四条计划所列失败和同轮旧 conftest 路径错误均保留。

R461 唯一 RED 为 6 项预期失败；唯一 GREEN 为 4 FAIL、2 PASS，后续阶段未运行。新失败已交实际 Astra R464，不能把命令契约接受写成 P0 软件接受。实际 API/physics/render 为 0；full NOT_RUN、native UNKNOWN、formal NOT_ACCEPTED。
