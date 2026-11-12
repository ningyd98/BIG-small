# R616 GL依赖身份覆盖与实际采集对比

R615的失败是清单覆盖小于loaded-origin分类范围。按同一组libEGL/libGL/libOpenGL/libnvidia规则，从当前ldconfig缓存枚举并固定44个canonical库，保留原23项及gpucomp。身份项仍只有path/bytes/SHA，别名与缓存来源放在清单元数据；未知或变化的已加载库仍拒绝。没有产品、运行时或驱动修改；清单中未加载的库不冒充实际调用。

对已交付R614代码开展一个新的R616额度，未重试R615/R613。相同side-Y75资产、320×240、seed613001、noise0.001、physicsdt1/240及关闭随机化。完整原对象路径：初始化/模型/MjData/reset/resetforward/相机/Renderer各1，3次采集及8次渲染（3RGB/3DEPTH/2SEG），原始转换5次、PNG校验8次、原自动退出flush1次。无预热、动作、物理步、IK、教师、模型推理、云付费或硬件操作。

唯一过程exit0，子进程回收且无存活所属组，backend及renderer关闭；所有计数started=completed/failed0，observer/audit/refused/errors为空，stderr为空，原GPU锁身份/大小/mtime未变。26个新run文件/3,500,406字节在分析前冻结，分析后成员、字节、SHA及mtime一致；426源码/资产、1451运行时、44GL、2辅助件身份一致，R615原失败3文件也保留。仅JSON/pstats/字节hash检查，未额外解码图像或读取旧raw/数据库。

| 同类计时 wall | R613原源码 | R616优化源码 | 描述性变化 |
|---|---:|---:|---:|
| 普通采集1次 | 65.739274ms | 43.340573ms | 降34.1% |
| 单独剖析采集1次 | 183.497138ms | 109.099450ms | 降40.5% |
| 原自动三帧flush | 176.280739ms | 159.949238ms | 降9.3% |

CPU同向，各模式完整wall/CPU差值与初始化/reset见diagnostic-summary.json。单次剖析总独占108.596911ms；互不重叠文件self：backend41.400201ms、dataclasses21.610006ms、observations21.120083ms、camera1.284285ms；递归或累计时间不相加。它说明实际普通采集路径存在改善，但不是完整连续spool或624秒历史动作的归因。

完整父进程反而从1.717232s增至2.068455s，子过程从1.579290s增至1.946012s；本轮新增严格GL身份覆盖/启动检查，不能用局部计时称整个进程普遍加速。每模式每源码仅1个样本，不作稳定态或统计显著性承诺，也不按3389帧外推。

三帧pass哈希数量2/3/3且同帧一致，reset实例为空，后两帧各76800实例ID；原16个报告文件hash匹配。UNBOUND/INCOMPLETE/SOURCE_CONSISTENCY_ONLY是普通未绑定采集的预期范围，不是native资格。没有软件修改，不重复测试或审查；原124通过的软件交付仍独立保留。下一步另行规划标记几何跟踪接入。原3次教师尝试、0/9资格、遮挡/fullspool问题、8秒/5秒及UNKNOWN/UNAVAILABLE不变。
