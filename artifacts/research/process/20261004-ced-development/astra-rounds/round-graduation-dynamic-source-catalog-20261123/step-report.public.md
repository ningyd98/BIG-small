# r593 开发实例的源目录和时钟复核

首次预检以 v10 上层试验协议查询源目录，产品函数返回 `registered schema/family pair required`。错误发生在预分配写入、场景重置和物理运动之前。修订仅涉及新增开发验证器及其测试。[错误原文、输入指纹与修订范围](plan.json)

r593 几何在源目录层使用 v4。显式选择 v4 和使用该标记家族的默认查询都得到 456 个文件，逐项路径与 SHA256 一致。压紧 JSON 的产品摘要为 `01f29ebf95837973d52c112d183e11a7abc361a750e42606f1811fad7c9ad04b`，开发工具按另一登记序列化规则得到 `f80d22e50fa46a1c294ddbfd65ce6d4aad04bc0f61e665340d670d80bf8eee38`。v5 对应另一配置，v10 源目录组合继续被拒绝。[已签视觉实例与两种摘要定义](../round-graduation-dynamic-qualification-20261123/allocation-vision.public.json)

两种后端分别绑定真实运行时步长。固定抓放夹具沿用默认的 0.0041666667 秒，r593 组件显式配置 1/240 秒。在 6,000 步时两者相差约 0.2 微秒。各自验证器接受自身时钟，互换时钟、错步号、错时间和跨 episode 的数据被拒绝。这项预检对构造的时钟序列做软件核对，真实物理运行另行计数。[七个身份的联合登记](../round-graduation-dynamic-qualification-20261123/allocation.public.json)
