# R386 Unicode输出路径前置修正计划

实际 **gpt-6-astra /root/astra_delivery_plan**；只规划。input-audit SHA256 `21fb35188cb168590e0e7cbdd12e39b36452727f9a7c4c318af29ab56daac120`，5 pins全部一致。

R384计划生成与执行器均把中文绝对前缀用于`json.dumps`默认ASCII转义后的文本替换，结果零替换，stage仍指向R383。原stderr确认line44安全门阻止；本席确认无R384 verification目录，没有进入driver/测试。保留这些原件，不修旧文件。

仅新建R386执行器/spec/前置及结果记录；继承R384目录、字段和回归门槛，不触碰R385分类器，不改产品/tests/旧runner。计划JSON中的两个stage已用下述纯数据转换生成并逐字段静态核对，可直接使用：

```python
def remap(value):
    if isinstance(value, str):
        for old in old_prefixes:
            value = new_prefix if value == old else value.replace(old + "/", new_prefix + "/")
        return value
    if isinstance(value, list):
        return [remap(item) for item in value]
    if isinstance(value, dict):
        return {key: remap(item) for key, item in value.items()}
    return value
stages = remap(parsed_r384_plan["execution"]["stages"])
for spec in stages:
    spec["env"]["BIGSMALL_R158_COMMAND"] = "r386_" + spec["name"]

```

`old_prefixes`为本仓库绝对R383、R384轮目录；`new_prefix`为绝对R386轮目录，JSON列出精确值。不得把JSON序列化作为转换介质；不改变字典key、cwd、解释器、PYTHONPATH、R377/R380/plugin/seed等输入路径。

- [ ] mkdir前检查**两个stage全部字段**：directory严格等于`R386/verification/<name>`；argv中basetemp/JUnit、全部输出env及预创建目录均绝对且位于相应stage。禁止输出中残留R383/R384；对照旧模板仅许可前缀和`r386_*`标签变化，节点/cap/插件原样。写纯数据mapping证明，未知已有stage目录停止，不删除。
- [ ] 核对本轮及继承pins、解释器身份、源稳定/独占、实际权限。继承R384全部输出目录mkdir与自身/祖先非symlink核验、新空basetemp、输出原本不存在检查；两个stage完整准备后才启动统一新360秒deadline。
- [ ] 仍串行58项/180秒、9项/60秒，各15秒清理；第一组通过才第二组，无重试。正确读取`accepted_prerequisite is True`，独立验证driver/child退出、精确JUnit、源不变与清理。不得以driver exit0冒充测试通过。
- [ ] 新记录保留R383的25FAIL/33PASS、R384前置停止/零新测试；R386通过只算限定软件回归。新失败保留并交下一实际Astra，不改源码、不扩大预算。R383独立打包/推送授权与范围不变。

本席仅完成数据级静态映射证明并写两个计划，没有创建verification目录、运行driver或测试。
