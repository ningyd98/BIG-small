# R385 生成链接行政分类修复计划

> **For agentic workers:** 主代理使用 superpowers:executing-plans 实施；无需另派代理或再请求用户确认。实际规划者 gpt-6-astra，agent `/root/astra_packaging_link_plan`。

**Goal:** 用R385新分类器副本正确记录local-only生成链接及gitlink，继续R383明确交付范围。

**Architecture:** 冻结R383输入，按节点类型读取元数据；600个精确链接只读link target字节，不读取目标载荷。所有新输出留R385。

**Tech Stack:** 现有`.venv/bin/python`标准库、Git只读索引查询。

**Spec:** 用户AGENTS.md、R383 plan.md/plan.json与R385 input-audit.json。完整输入SHA、输出路径及验收条件见同目录plan.json。

## 证据与根因

R383 `classify_intake.py:71`在分类前无条件assert拒绝symlink，首次触发pytest的`test_b_terminal_publication_cocurrent`。原工具chunk `3441a8`退出1；原stderr仅在会话，未落盘，input-audit是转述，禁止重造“原件”。另需避免原mode逻辑把两个gitlink目录记为普通文件。

本席只读核对：原inventory 21480节点＝20878普通文件＋600链接＋2 gitlink目录。600链接唯一、均为`??`、位于`implementation/.../persistent-basetemp/`，其中586个`*current`、14个生成fixture（包含测试用escape/outside命名）。600个live lstat/readlink/size与audit相符，mtime与原inventory相符，词法目标均在工作区；未读取目标载荷。两个gitlink索引均为`160000 ddbeb92a1aa1dfa8039f6260d6b5887c58072383`。只根据这600个已审路径许可，不泛化“symlink安全”。

规划期间一次`python`命令不存在，原会话chunk `d9de8d`保留，未有落盘原stderr；本席Astra在此固定使用现有`.venv/bin/python`完成只读核查，未改环境或产品。宽输出截断不作完整读取证明，关键输入另做定向核对。

## 冻结输入

- `artifacts/research/process/20261004-ced-development/astra-rounds/round385-delivery-generated-link-classification-20261101/input-audit.json`：`d63259b3ad234626e103809034e21c0abbdd6186e13e0fce999039163bd17134`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/plan.md`：`9636d82f5ec4635ede098db35f040c312bee2057d80aa7c031ec1ca44df3d4f7`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/plan.json`：`38aac87f9d9939084e565f80b243b64cc76e190434cdae431cd10deb50a84655`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/classify_intake.py`：`7ce0afbab7725ddc01e0b40268ce74cbdb35e0ff07273e5fc313242076cadf60`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/initial-inventory.json`：`580e713426cc4d1d8c09d6ad83342d585bf8ac6bd68efd8b3751c710cfdf8561`
- `artifacts/research/process/20261004-ced-development/astra-rounds/round383-workspace-github-delivery-20261101/initial-status.porcelain-z`：`ee74fc15f71a3a79cc11f86e5ee654c74d1e3e0ac538e765fbbbaea9671abcfd`

## 唯一实施任务与验收

- [ ] 实施前重核全部pins、原inventory节点及R383 Git前置条件。无并发改动原节点；R384独立工作不纳入本轮。R385输出须全新，禁止覆盖旧文件。
- [ ] 复制R383 classifier至R385 `classify_intake.py`，明确原输入目录与新输出目录；不改原classify决策规则。普通文件延续size/mtime/hash。读取`git ls-files --stage -z`将两个gitlink记为`160000`及原OID、local-only、载荷hash=null，不递归。
- [ ] 在`is_file/open/digest`之前分支处理symlink。链接记为`120000`，通过`lstat/readlink`保存target文本、`SHA256(os.fsencode(target))`及target字节数、节点size/mtime，载荷hash=null；前后读一致。不resolve、不打开目标。许可严格限audit的600精确路径，且原classify为local-only、原status=??、生成目录归属及原target/元数据均匹配。
- [ ] 对path/target做纯词法边界检查；既存父级逐层lstat，不沿链接行走。待selected/源代码链接、名单外或越界链接、链接祖先及不明类型blocked并非零退出。缺失目标仅记dangling，不修复。测试中的outside文件名本身不是越工作区证据。
- [ ] 用现有解释器执行副本一次，保存原生stdout/stderr/退出码；新manifest、summary、selected清单、local-only精确清单及可选原inventory/status gzip均写R385/preflight。blocked须进入记录并阻止stage。
- [ ] 独立核对输出与原inventory路径集合相等、无重复；21480总数及20878/600/2节点数守恒，三种决策互斥完整且blocked=0。600链接全local-only/120000、两个gitlink全local-only/160000，selected无链接；regular决策沿用原规则。计数与字节总量分别报告常规载荷、link target及gitlink，凭据内容不读、不hash。
- [ ] 核对冻结输入SHA、600节点/target指纹、gitlink mode/OID及普通文件元数据与载荷hash证据；验证gzip解压精确等于原bytes并保存压缩/未压缩hash。新报告诚实保留首次失败事实。无需为本低影响行政修复新增或运行产品测试。

## 保留与交付边界

所有local-only原件及600链接原位保留，两个gitlink内部dirty不清理。若主代理继续R383的`.git/info/exclude`，只追加已审锚定转义精确路径并保存原内容/hash，禁止隐藏源、测试、计划或作者报告，禁止改`.gitignore`。不修改R383原classifier、inventory/status、src/tests、历史原件，也不处理R384前置目录或accepted_prerequisite。

主代理新写R385/step-report.md与phase-summary.md，记录一次分类结果、守恒证据和保留边界，汇入R383阶段交付。R383正常精确路径stage/commit/push与本地/上游/远端SHA核对仍适用，软件门槛仍须独立满足。排除清单、指纹和压缩inventory不等于完整raw上传或远端复现包。

行政成功仅表示分类exit0和上述不变量通过；真实运行0、研究正式验收不新增。新根因、输入漂移、范围扩大或计划外失败应保存原生输出并交下一Astra轮，不能重跑覆盖。本席只创建本计划两文件，未实施分类、跑测试或作Git写操作。
