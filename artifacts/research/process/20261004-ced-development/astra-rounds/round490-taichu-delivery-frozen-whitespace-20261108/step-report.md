# R490 步骤报告

实际 Astra 逐条固定 13 个原字节例外，保留 CSV CRLF、diff context、traceback 与半写 JSON；未清理历史字节，未修改全局 Git whitespace 规则。默认全量检查原 rc2 保留，精确例外之外的全部路径按相同默认检查 rc0。

采用独立临时 index，只加入 R486–R490 五目录；每个 staged blob 与实际文件字节一致，公开载荷不包含模型 raw、权重、SDK、wheel、deb、headers、venv、JIT、数据库或凭据。共享 HEAD/index 与无关 service.py 在交付前后单独核对。

Git 提交以已交付 8b4a88b 为父，新建指定研发分支，不切共享 checkout；推送及本地/上游/实时远端三 SHA 的最终结果保存到 excluded local receipt，避免提交自引用。本文件本身不证明推送完成。
