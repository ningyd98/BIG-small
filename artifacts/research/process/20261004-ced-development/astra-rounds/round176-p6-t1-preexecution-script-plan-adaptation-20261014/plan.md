# R176 — R175 预执行元数据脚本适配恢复

实际规划者：gpt-6-astra（/root/astra_status_plan），2026-10-14。冻结后等待 ROOT 输入与全文门控；本轮不执行修复。

## 独立判定

这不是 pytest 或工具运行失败。两个草稿从未执行：prepare-metadata.py 用 D174 变量指向实际 R175 目录，却在180/382行引用未定义 D175；294行读取 R175 plan 中不存在的 original_failure.six_raw。根因为旧轮次脚手架的名称及JSON合同适配遗漏，不构造 NameError/KeyError 运行记录。

已真实核对 R174 scope-proof.json 的 original_green.raw_preserved：准确六条原始文件 locator，历史为7tests/5PASS/2FAIL、product1/runner2、spent1/0。该原件61009B，SHA256 b1812cd66c03751e23efc111aef0492f636f4acd6c0599f1d7553d5545975fdb。全部输入、六raw及四草稿完整字节见JSON。77输入、87连续性检查全匹配；嵌入before/after字符串作为JSON数据核对真实前后helper，不执行脚本。

## 唯一允许修改

只改 R175 implementation/prepare-metadata.py 与 run-recovery7.py。统一当前目录变量 D175，独立保留真正R174历史目录；用钉住的真实 scope-proof.original_green.raw_preserved 替代不存在字段，验证六raw并作为明确辅助输入，不修改旧62输入合同或削弱61/48固定项检查。

两脚本固定已认可candidate：135950B，SHA256 bb22fb6abd3f047de06da30252ec8c3aeef83082fba934d249dd54187fd9e688；gate必须与此常量相等，不能从gate任意重绑定。runner核对现有 sidecar 的调用thread/native_thread与每个init/close真实坐标一致；不增加或伪造producer字段。完整分母、pid、类、方法恢复、节点和四集合检查保留。

产品、helper、七正文、13旧工作报告和所有历史原件此时不动。两账本此时不动；原R175准备动作获门控后才按原合同归档并刷新13报告。ROOT独立第三槽脚本准备不属于本轮修复范围。

## 捕获与额度

新增执行次数为0。原R175三个槽各used0/remaining1，author HELD，ROOT HELD_PENDING_ROOT_GATE；保留原120s/600s/120s与exact argv/env。R158仍3spent/12HELD，不恢复旧A/Git/静态/测试额度。

ROOT先读计划/输入，再读两修正脚本完整文本、差分和实际shell捕获命令。使用标准shell noclobber及exec精确.venv argv独占保存真实stdout/stderr；不增加helper/subprocess层。准备流使用原声明路径，outer recovery runner另存implementation/recovery-runner-stdout.txt与stderr.txt，与child raw区别。工具返回另存，未知tool-native streams仍null。脚本stdout只给少量路径/完整SHA/计数，完整结果留JSON。

输入/重定向/运行任何新失败都停止，保留部分原件，不重试。角色正常reservation/consumption沿原R175流程，只各一次。ROOT实际准备、恢复七节点、独立结算及fresh review门顺序完全保留。

## 边界

本轮只恢复可门控的元数据草稿。原R174 7PASS、原R158 5PASS2FAIL均不改。未执行的资源包装及accessor不取得历史覆盖；不宣告T1/B9/T12、原生物理、实际或正式验收。plan.json列出所有准确路径、SHA、字段、修改区和输出边界。

