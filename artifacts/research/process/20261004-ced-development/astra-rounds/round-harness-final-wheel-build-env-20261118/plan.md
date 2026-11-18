# Astra：最终wheel的隔离构建前提

实际 `gpt-6-astra`，PLANNED_NOT_RUN；4项SHA见JSON。首次命令在缺setuptools的app venv禁用build isolation，导致声明的setuptools.build_meta无法导入，退出2；这是构建调用前提错误，不改产品。保留build.log原件。

仅重建1次：沿用此前成功的默认PEP517隔离命令 `.venv/bin/python -m pip wheel --no-deps --wheel-dir <新目录> .`，去掉--no-build-isolation，使用临时隔离构建环境/既有缓存。不向app venv安装升级任何依赖，不改pyproject/源码/测试。新wheel记录SHA，再以既有clean H1venv `--force-reinstall --no-deps` 安装一次。

源码树外清除PYTHONPATH/PYTHONHOME与模型凭据，复用CPU help/version/validate/doctor/prepare/evidence/pipcheck；prepare用全新目录。核验实际导入installed wheel、console entrypoint与全部包内源文件/数据哈希匹配当前冻结源，保存原始输出及build前后源SHA。任何新失败停止交下一Astra，不循环构建。0GPU/renderer/model/API，无新增模型额度；已完成7例审计component3/7、physical4/7不变。
