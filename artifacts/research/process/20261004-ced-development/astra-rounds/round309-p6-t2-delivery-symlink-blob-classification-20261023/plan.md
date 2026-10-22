# R309：交付预检的精确符号链接分类

实际模型：**gpt-6-astra**。仅规划，未执行预检或Git写入。

## 原失败与实物

R308原preflight（b4ab0b）exit1，第15行只允许regular文件；报告未创建、没有Git写入。实测六个pytest current别名是符号链接，目标为各自basetemp中原绝对路径；两个已排除dirty physics gitlink没有触发该错误。原失败不改，六链接路径、原始readlink字节hex/长度/SHA与lstat模式均已固定在plan.json。

## 限定修正

plan.json保存完整修订调用：lstat分类，只有明确六个path+target匹配的symlink允许，源blob使用os.readlink原始字节、Gitmode120000，不跟随或hash目标目录。普通非可执行regular文件使用100644和源字节，读取禁跟随链接；未知类型/链接一律停止。原分支、HEAD、空index、源码范围、数据库排除及100MiB检查保留，只将本R309目录加入明确轮次范围。

运行结算及R308压缩恢复已完成后，ROOT只执行一次新预检，0retry。成功报告写原仍不存在的R308/git-preflight.json，新actual写R309/git-preflight-actual.json；旧失败永远保留。六个原链接可按精确路径stage保存，不删除、改成相对路径或批量ignore。

## Git blob核对与交付

明确路径stage后读取index的mode/objectID，要求路径集合恰好获准：120000的raw Gitblob等于readlink文本原字节，100644等于普通文件源字节，不能把链接目标内容当blob。保留gzip/九个原case、聚合local-only、DB边界和dirtygitlinks。预检后新增receipt只作为明确新增清单条目，不递归自hash。

核对后按既有授权commit/push研发分支，保存本地HEAD、upstream、remote三SHA一致的实物回执。无新产品/测试/runner/gate/角色修改或运行额度，无新通用管理框架。链接保留只证明原alias字节，不等于完整/可移植远端DB复现包。任何新的实际失败保留现场并停止相关交付，不改旧证据求通过。
