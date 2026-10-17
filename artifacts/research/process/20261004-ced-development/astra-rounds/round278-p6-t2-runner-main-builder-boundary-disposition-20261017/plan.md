# R278 runner main 文本边界处置计划

实际模型 gpt-6-astra。仅恢复原 R276 源码准备，不新增任何运行、验证、静态、SQL、Git 或审阅额度。

## 原始失败及真实原因

原 V8 在最后 display 字段 replaceOnce 抛出 unique main source boundary required。该字面量有28个前导ASCII空格，物理 original-template-main 第239行实际27个：错误匹配计数0，真实整行计数1。原 main 模板与冻结 R268 runner 的唯一 def main() 起始尾部逐字相等。

未到任何nested tool/文件写/final store；丢失partial main不可恢复为历史before。structured返回、numericexit、chunk、独立流均null；完整可见JS已保留，但原工具参数末端LF无独立字节观察。不是产品或测试失败。

## 最小恢复

同一Sol在ROOT接受后放弃旧易失builder，从已保存四个完整物理draft与原template构造一个**新的完整main**。可使用已证明唯一27-space整行边界，或显式编写完整main；禁止strip/猜测边界/重放失败call。先持久保存main、consumer和完整runner候选，再native Add，保全真实参数和返回。原四draft、原JS、所有旧candidate/native不覆盖。

允许差异仅原R276必要路径映射、新round输出、wait/dual分别验收、dual独有被动consumer及有限display。成功reservation后全部lifecycle/finally、原600+15/900/540、实际raw/resources、同key SPENT不退款均保持。完整header/拼接/所有函数必须ROOT全文审，不能靠新header绕过语义验收。

consumer的旧worker_id对象关联只按已批准R277改worker_object_id；原draft保留。插件旧f0ed只经D277物理before解释，实际新48e4与ROOT接受需在最终runtime门核实。

## 门禁及证据

1. ROOT审本计划、完整原失败、15个物理输入和边界证明。
2. Sol只新源码准备，保存完整candidate、native、after、limited diff与来源报告；runner此前不存在，before=null，绝不伪造partial main。
3. ROOT完整source/native/input/argv/角色门，逐字段核R276三命令原合同；出现新根因即STOP回Astra。
4. R276三个原once仍0/1；本轮不建角色、不执行runner，不改产品/fixture/STATE/PHASE。

完整输入SHA及四draft全bytes/base64/mode见 input-observation.json、draft-before-manifest.json。冻结后STOP。
