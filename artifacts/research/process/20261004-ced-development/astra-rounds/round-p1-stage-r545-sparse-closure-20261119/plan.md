# 同一冻结提交补齐 R545 预检依赖

## 原始证据

- 首次 stage 在 R545 configure_overlay 打开其固定证明文件时 FileNotFoundError，原候选目录仅物化了 launcher。证明在冻结 4bdb64ebd220b37b728de193706fed83a9813791 中是 4426 字节、Git blob 58a851c17e762e15f7e0f35187ffd99b5c13fe0d，SHA256 654de3974d33c6519bf7c211c6a76d1c0f1ec943d7435f595f6ee7dbb9d9bedc。保留原 partial preparation；canonical owner 尚未创建、0 BEGIN。

## 限定工作

- 仅在已冻结的 development sparse checkout 扩充已有 sparse pattern，加入上述相对路径；若 R545 实际入口存在更多受控相对读取，可一次列出整 R545 已跟踪依赖及链接所至的同提交路径，不切换 revision。按真实源码静态引用与 preflight 实际打开/导入确认闭包；保留旧 patterns，不 reset/checkout 其他内容。逐件以 git ls-tree/show 与现文件验证 mode、blob、长度、SHA；软链本身和解析到的已登记目标分别核验。解释器、外部已绑定 r505 .pth 与依赖只沿现有冻结验证，不临时下载或换装。

## 运行前置

- 输入哈希、Git clean 受控树、HEAD/tree、wheel、真实配置、已登记 allocation 修前修后相同。旧失败目录及日志保留，新输出目录重新 stage；不得手造 proof 或绕过其内置 SHA。

## 验收

- 在受控 r505 解释器以 -I -B 调用原 launcher --preflight，核实正常退出、源绑定、实际导入位置；通过正常已安装入口重做 stage，输出独立可核、旧四槽无变化。缺失/已变证据应继续拒绝。stage 成功且正常原前置满足即可执行已授权分配，无需额外付费审批。
