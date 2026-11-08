# R501 — 已捕获16个DEV场景的条件B

实际规划模型：gpt-6-astra；仅规划。完整冻结输入与SHA见plan.json。实际A checkpoint已核8/8完成、JSON4/4严格通过；16case processor预检及来源hash全通过。批准复用当前resident做JSON-only B，一case一次，顺序positive01–12、negative_absent01–04，不再load/warmup。

仅新artifact B helper/scorer/授权文件；原system/user字节、RGB/depth图顺序来自冻结messages，逐case tensor/IDs/hash必须匹配processor预检。保持v1来源，不能套v2；原320×240图不改，官方processor处理照旧。各case token长度单独记录，不冒称S01的1030。instance/场景/旧输出只用于离线评分，不入模型。原A greedy512/beam1/seed0/usecache、thinkOFF、SDPA/248FP8/BF16、实际kernel/环境、D28/EOS适配全不变，每request新约束状态。

严格原schema评分；normalized1000先检查整数和0..1000，再依原messages.py换320×240像素。正例分别统计object_geom目标命中、target_region_geom区域命中及depth/valid-mask有效性，分母12与覆盖并列。4个purple缺失任务记录双null+skills空拒答、confidence0另核；非空skills是动作建议而非实际误动作。3D误差/P90均NOT_MEASURED，旧DEV非heldout、无硬件执行率。raw/IDs/masks/callback/时延/显存/FP8和partial均保留，不清洗输出。

授权文件冻结plan、A、source/messages/processor及新helper/scorer SHA后通过原等待接口启动。时间估计采用16×(A最慢JSON端到端×1.25+0.25秒)+15秒（约4分钟经验估计，B输出变长仍可能partial），启动前剩余窗口须足够，resident最多等待5分钟；否则NOT_RUN，不重载。**B硬截止16:09 UTC、总16:19:20**，每request≤min(180秒,剩余B时间)，最大B16/总24/唯一load不变。不改512凑时间；格式/定位负例继续预登记顺序，运行异常/超时停止并记partial。保留末10分钟报告Git，输入变化与子集限制明确披露，沿用原R491显式路径与三SHA交付。
