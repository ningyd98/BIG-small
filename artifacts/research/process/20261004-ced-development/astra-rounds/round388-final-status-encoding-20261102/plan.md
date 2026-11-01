# R388 终态porcelain编码断言修正

实际 **gpt-6-astra /root/astra_delivery_plan**，仅规划；输入文件SHA256见plan.json。原toolchunk `b6101f` stdin line13预期` m`，实际为两个精确gitlink的` M`，因此后续HEAD/0:0/最终收据步骤未执行。原stderr只在会话，新增记录须标明事实转述，不伪造native原件。

已读取本机官方git-status manpage：porcelain v1将子模块改动统一表示为大写M，区别于人读short输出的小写m。当前只读确认：HEAD `67d02434663fb9cf72aadbb3b743a49a7370f04a`，ahead/behind 0/0，cached diff空；两gitlink索引160000、stage0与nested HEAD均为`ddbeb92a1aa1dfa8039f6260d6b5887c58072383`。这是成功push后的行政断言错误，非产品或Git数据失败。

- [ ] 新建R388小型行政验证器/报告；保留旧status、push输出及全部旧证据。按`git status --porcelain=v1 -z --untracked-files=all` NUL解析原始bytes，XY=`b" M"`且路径只能是JSON列明的workspace-baseline和workspace-h3。禁止split空格、大小写归一化或宽泛允许其他dirty。
- [ ] 独立验证：最终cached diff空；worktree差异仅两个gitlink；HEAD树、index mode/OID/stage及两个nested HEAD全与原值相同；非gitlink无tracked/untracked差异。验证读操作前后index hash不变，不要求两个内部dirty仓库变clean。
- [ ] 写R388期间仅允许精确新行政文件；若需交付它们，仅一次小型明确路径commit及正常push既有研发分支。此前已推送提交不为补报告而重push，不amend历史；提交后push前ahead1是中间态，不能提前跑最终0/0断言。
- [ ] 最终重新核对本地HEAD、upstream、live ls-remote三SHA一致且0/0，status仅两个原gitlink。独占写私有`.git/r383-github-delivery-20261102/final-receipt.json`记录最终SHA、checkpoint `13579b8ed9face9e90cd6947073ab2101b558e96`、精确gitlink及diff检查/原输出hash。该外部收据无需再提交，避免自引用提交循环。

仅修行政schema并补收据；67CPU与fullfsck原通过证据哈希保持，不重跑。禁止产品/tests/嵌套仓库或旧证据修改、隐藏dirty、reset/clean/force/改写历史、发布完整私有index/metadata。新实际错误保存并交下一Astra，不放宽白名单。本席未stage/commit/push或运行测试。
