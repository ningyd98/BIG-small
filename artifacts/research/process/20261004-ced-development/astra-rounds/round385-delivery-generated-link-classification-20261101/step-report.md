# R385 节点类型分类结果

按实际Astra计划运行新分类器一次，退出0，原生stdout/stderr保留。21480个唯一路径与初始清单完全一致：20878普通文件、600local-only链接、2local-only gitlink。941精选普通文件，20539节点本地保留；blocked=0，selected symlink=0。普通载荷、链接target字节、gitlink分别计量；600链接只读节点元数据和target字节，未打开目标，原source overlay和所有冻结pins保持。

两个gitlink记160000/原OID；链接记120000、target SHA与payload_sha256=null。压缩manifest及初始inventory/status副本均验证解压字节一致，精选和本地排除集合互斥完整。原R383分类失败保留在会话工具chunk3441a8，未冒充落盘原stderr。没有删除、产品测试或真实运行；具体计数/哈希见preflight/classification-summary.json。
