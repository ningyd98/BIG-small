# R316：已使用 token 的最小接续

实际规划模型：`gpt-6-astra`。仅静态规划；未运行产品、测试或 stdlib probe。

## 证据和根因

当前 G1 `_decode_memo_owned_here` 只捕获 `ValueError`。父解码退出时 finally 已 reset token；先前复制的 active Context 仍可能持有同一个 memo。CPython 源码确认：reset 先检查 token 是否已使用并抛 `RuntimeError`，随后才检查 Context 不同的 `ValueError`。这是静态路径确认，尚无产品动态失败回执。[CPython v3.12.0 源码](https://raw.githubusercontent.com/python/cpython/v3.12.0/Python/context.c)

## 唯一产品改动

只在 `_decode_memo_owned_here` 的 token reset 小范围 try 中替换一次：

```diff
-    except ValueError:
+    except (ValueError, RuntimeError):
```

仍返回 False，走已有新作用域分支；不得扩大其他异常捕获、吞掉 finally 错误或改 memo／校验规则。

## 同一微回归补充

保留当前测试全文快照；从文件开头到 primary `assert not duplicate` 行的字节必须完全不变。只在原单节点后续逻辑补两种情况：在父 decode 活跃时复制 Context，分别在父正常结束、父有意 BaseException 退出后，再于副本中解码同一合法输入。检查真实重验证、新 memo、新实例、原字节／digest 和双方清理；不得复用父成功项。

复制 Context 也会复制测试 spy 的 stack；若需新 root 计数，只清空测试专用 stack，必须保留产品 memo 的复制值来触发待修边界。新增断言写入现有 case 记录，不引入新测试节点或工具框架。

## 接续和边界

ROOT 复核输入 SHA、全量 before／after 与原 primary 前缀后，更新既有 R315 新世代 gate。原 GREEN、writer 均 HELD 0/1，直接继续原 GREEN 一次，再按 R315 顺序执行 memory 和原 R311 SQLite HELD。不新增槽、不重复 RED、不运行额外 probe；全部原限时和 retry 0 保持。

保存 G1、原测试、原 diff／generation map／RED 原件；新映射另存，不改冻结计划。任何新失败或需要扩大所有权实现范围，停止受影响步骤并回 Astra。未完成 GREEN 前不宣称修复通过；全 T2 边界不变。

输入 SHA、角色状态、受保护前缀 SHA 和准确实施范围见 `input-observation.json`、`plan.json`。
