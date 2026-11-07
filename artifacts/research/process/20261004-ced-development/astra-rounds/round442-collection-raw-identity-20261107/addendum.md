# R442 补充：隐式双pass帧与实例原件

Actual gpt-6-astra，2026-11-07。本补充覆盖R442“成功全组每帧必须width×height instances”的过宽要求，原plan.md/json保持原样。仅R439新recorder/reader及原已计划测试范围；没有新测试阶段、physics/render或重试额度。

## 原始静态依据

backend `_capture_cached_observed` 调用 camera._capture(include_instances=False)；在存在operation observer时 `_update_sensor_frame`仍通过该CAPTURE路径。camera._capture先产RGB、depth及两个真实pass_state_hash，初始化instance_ids=()、instance_labels={}；只有include_instances=True才执行第三次segmentation render并生成每像素instance数组。原显式`capture_sensor_frame_with_instances`和T1逐步sampler走三pass。

因此隐式缓存刷新产生的零长度instance原件是**实际未请求该通道**，不能标成丢帧/实例缺失，也不能伪造width×height数组。反之，三pass必需帧的空数组仍是不完整。

## 按实际采集用途的规则

|用途|真实pass数|instance原件要求|完整性|
|---|---:|---|---|
|REGISTERED_PER_PHYSICS_STEP|3|width×height有符号i32原数组及原labels|缺数组/标签/第三pass为不完整；不能降级成隐式帧|
|REGISTERED_ACTION_BOUNDARY（原pre/terminal等已登记边界）|3|同上|同上|
|IMPLICIT_SENSOR_CACHE_UPDATE|2|原tuple()、dict{}和其存在状态，实际blob可为0字节|明确instances_requested=false、instances_available=false、instance_count=0、reason=NOT_REQUESTED_BY_REGISTERED_CAPTURE；不是SOURCE_MISSING|

各frame仍保留原RGB-D payload/checksum、camera-state、joined physics-state、两个或三个原pass hashes及原字段、acquisition/operation ID。隐式帧仍进入全部分配帧分母、原RGB-D/geometry可用性和完整物理state一致性检查；任何RGB/depth/原状态不一致、缺原件或未知视效仍原样失败，不能因为instances非必需而忽略。不得删除隐式帧以获得有限分数；也不得用其填补必需逐步三pass或边界采集槽。

## 来源证明与计数

capture_role不是调用方声明：新recorder在CAPTURE BEGIN根据实际source-owned显式capture上下文、backend `_step_capture_count`本次真实增长（T1在采样前分配）、当前operation/physics_step及已注册调用日程记录角色和counter。逐步计数增加只允许对应一个新的三pass采集；显式capture在原scope内；无新逐步槽/显式scope的缓存更新必须落在固定backend `_update_sensor_frame`调用位置（日程含RESET/step返回处），否则UNKNOWN。不要只按“数组空/两个hash”猜角色，否则坏三pass会被洗成合法双pass。

新reader重放注册日程、全部physics/operation/guard及capture序列，验证每个必需物理step唯一三pass槽、边界三pass与额外缓存双pass位置及对应计数；所有role/source字段与此矛盾即拒绝，不信缓存标签。当前两个backend捕获方法均由同一个observer汇流，不另装observer或放开重入。

双pass要求两个hash彼此相等且与该capture原camera/physics状态依据一致；三pass相同原则扩为三hash。`render_passes_observed=Σ各真实capture原pass数`，同时分列scheduled_three_pass_acquisitions、boundary_three_pass_acquisitions、implicit_two_pass_acquisitions和failed/partial pass计数；不能将隐式帧计为三pass。隐式日程数量及上界沿R439已登记预算；原逐步12960及边界上界不被隐式额外帧改写，实际总acquisition/总render和输出资源单独核对原上限。

## 实施与验证承接

只修R442新子类帧meta/reader验证和原T2/T3测试：

- 三pass完整实例原件roundtrip；三pass空实例不得冒充双pass。
- 合法缓存双pass原空tuple/labels、0字节instance blob可完整roundtrip，instances不请求理由原样保留。
- 假role标签、逐步槽缺失、位置错误的额外双pass、任一双pass hash/state不符均失败。
- 真实RGB-D/物理join不完整仍失败，完整隐式帧不因合法空instances误判缺失；全部分配帧保留。
- 总render按3×已成功三pass+2×已成功双pass及真实partial统计核对，不新跑renderer验证。

本次仅静态元数据读取与本addendum写入，product edits/tests/physics/render=0；不修改旧backend/camera/RawV3 schema、不重写R442原计划，不增加R439剩余额度。
