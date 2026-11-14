# 硬限位失败诊断修复计划

## 1. 问题定义

**本轮要解决的核心问题**：3个样本因硬限位失败，但现有 `physical-evidence.json` 只保存布尔标记 `joint_limit_violation`，缺少具体越界关节、位置、上下界和幅度记录，无法判断根因是监测覆盖、关节映射还是控制轨迹问题，阻碍了下一步修复方向的确定。

**为什么阻碍进展**：当前无法回答以下关键问题：
- 哪些关节触发了限位？（7个机械臂 vs 2个手指）
- 越界幅度是多少？（数值误差 vs 真实越界）
- 越界发生在哪个关节位置？（上界 vs 下界）
- 在线监测与评价的边界定义是否一致？

缺少这些信息，无法区分假设A（手指覆盖）、假设B（映射不一致）和假设C（轨迹不可达），也无法制定下一轮修复计划。

---

## 2. 根因分析与待验证假设

| 假设 | 描述 | 优先级 | 验证条件 |
|------|------|--------|----------|
| **假设A** | 越界来自手指关节，在线监测未覆盖 | P2（低） | 诊断数据显示手指关节触发限位 + 在线日志无对应告警 |
| **假设B** | 机械臂关节映射或边界定义不一致 | P1（高） | 诊断数据显示机械臂关节触发限位 + 在线与评价边界不同 |
| **假设C** | 控制轨迹本身不可达 | P1（高） | 诊断数据显示大幅越界（>1e-3 rad） + 目标姿态或路径有问题 |

**已确认的事实**：
- 代码审查显示在线安全检查与独立评价均检查9个关节（7个机械臂 + 2个手指）
- 判据实现在 `episode_evaluator.py:142-149`，使用相同的容差 `1e-4`
- 3个样本的限位均发生在 `APPROACH` 阶段

**验证策略**：先生成诊断数据，再根据数据特征确定具体假设。

---

## 3. 限定修改范围

### 3.1 可以修改的文件

| 文件 | 修改内容 | 理由 |
|------|----------|------|
| `src/cloud_edge_robot_arm/research/freeze_evidence.py` | 新增函数 `_save_joint_limit_diagnostics()` | 在检测到限位时额外保存诊断数据 |
| （测试脚本，新建） | `scripts/diagnose_joint_limits.py` | 重放3个样本并生成诊断数据 |
| （分析脚本，新建） | `scripts/analyze_joint_limit_diagnostics.py` | 分析诊断数据并生成根因报告 |

### 3.2 可以增加的函数/类/字段

- **新增独立诊断文件格式**（`joint-limit-diagnostics.json`）：
  ```python
  {
    "episode_id": str,
    "violations": [
      {
        "physics_step": int,
        "sim_time_s": float,
        "joint_positions_rad": [float, ...],  # 7个机械臂关节
        "joint_ranges_rad": [[float, float], ...],  # 7个上下界
        "finger_positions_m": [float, float],  # 2个手指关节
        "finger_ranges_m": [[float, float], [float, float]],  # 2个上下界
        "violated_joints": [
          {
            "index": int,  # 关节索引（0-6机械臂，7-8手指）
            "type": "arm" | "finger",
            "position": float,
            "lower_bound": float,
            "upper_bound": float,
            "violation_magnitude": float,  # 越界幅度
            "bound_type": "lower" | "upper"
          }
        ]
      }
    ]
  }
  ```

### 3.3 必须保持不变的部分

- `PhysicalSample` 数据类（避免影响其他功能和存储开销）
- `PhysicsStepObservation` 数据类（后端接口稳定）
- `episode_evaluator.py` 的判据逻辑（验证一致性，不修改）
- 正常样本的存储结构（不增加开销）

---

## 4. 实施步骤

### 步骤1：扩展诊断数据保存逻辑

**操作**：
1. 在 `freeze_evidence.py` 新增函数 `_save_joint_limit_diagnostics()`
2. 在检测到 `joint_limit_violation` 时，从 `PhysicsStepObservation` 提取完整关节数据
3. 保存到 `<episode_dir>/component/joint-limit-diagnostics.json`

**验证条件**：
- 函数能正确提取9个关节的位置、速度、上下界
- 能识别具体越界关节和幅度
- 文件格式符合上述 JSON 结构

**失败回退**：如果提取失败，记录错误并继续评价，不中断运行

**代码变更点**：
```python
# 在 freeze_evidence.py 中新增
def _save_joint_limit_diagnostics(
    observation: PhysicsStepObservation,
    output_dir: Path,
) -> None:
    """当检测到限位违规时，保存完整诊断数据"""
    # 实现：提取关节数据、计算越界关节、保存JSON
```

---

### 步骤2：编写重放诊断脚本

**操作**：
1. 创建 `scripts/diagnose_joint_limits.py`
2. 读取3个样本的原始输入（RGB、深度、姿态）
3. 重新运行评价，触发诊断数据保存
4. 验证生成的 `joint-limit-diagnostics.json`

**输入**：
- `development-043003` 原始输入目录
- `held-out-044009` 原始输入目录
- `held-out-044011` 原始输入目录

**输出**：
- 3个样本的 `joint-limit-diagnostics.json`
- 每个文件包含所有限位物理步的完整诊断数据

**验证条件**：
- 诊断文件存在且格式正确
- 违规步数与原始 `physical-evidence.json` 一致
- 至少有一个样本的诊断数据包含越界关节信息

**失败回退**：如果重放失败，检查输入文件完整性，必要时从备份恢复

---

### 步骤3：分析诊断数据并确定根因

**操作**：
1. 创建 `scripts/analyze_joint_limit_diagnostics.py`
2. 读取3个样本的诊断数据
3. 统计越界关节分布（机械臂 vs 手指）
4. 检查越界幅度（数值误差 vs 真实越界）
5. 生成根因分类报告

**输出**：
```markdown
# 硬限位失败根因分析报告

## 样本汇总
| 样本 | 违规步数 | 机械臂关节违规 | 手指关节违规 | 最大越界幅度 |
|------|----------|----------------|--------------|--------------|
| development-043003 | N | N1 | N2 | X rad/m |
| held-out-044009 | N | N1 | N2 | X rad/m |
| held-out-044011 | N | N1 | N2 | X rad/m |

## 越界关节分布
- 机械臂关节X: N次，平均越界 Y rad
- 手指关节X: N次，平均越界 Y m

## 根因判断
- [ ] 假设A：手指覆盖（手指关节违规 + 在线无告警）
- [x] 假设B：映射不一致（机械臂关节违规 + 边界不同）
- [ ] 假设C：轨迹不可达（大幅越界 >1e-3）

## 下一步修复方向
基于根因判断，推荐的修复方向...
```

**验证条件**：
- 报告明确标识属于哪个假设
- 提供具体越界关节、位置、幅度
- 给出下一轮修复计划的输入条件

---

### 步骤4：对比在线监测与评价边界

**操作**（仅在假设B成立时）：
1. 从在线运行日志提取关节边界定义
2. 从 `PhysicsStepObservation` 提取评价边界
3. 逐关节对比，标识不一致的边界

**输出**：
```markdown
## 关节边界对比

| 关节 | 在线下界 | 在线上界 | 评价下界 | 评价上界 | 差异 |
|------|----------|----------|----------|----------|------|
| joint_0 | X | Y | X | Y | 一致 |
| joint_1 | X | Y | X' | Y' | **不一致** |
...
```

**验证条件**：
- 标识出所有不一致的关节边界
- 确认不一致是否导致越界判定差异

---

## 5. 验证方法

### 5.1 诊断数据完整性指标

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 诊断文件覆盖率 | 3/3 样本 | 检查文件存在性 |
| 字段完整性 | 100% | 验证 JSON 结构 |
| 越界关节识别率 | ≥1 个样本 | 检查 `violated_joints` 非空 |
| 关节数据一致性 | 9个关节 | 验证 `joint_positions_rad` + `finger_positions_m` 长度 |

### 5.2 根因分类标准

| 假设 | 判定条件 | 证据要求 |
|------|----------|----------|
| 假设A | 手指关节违规 > 50% | 诊断数据 + 在线日志对比 |
| 假设B | 机械臂关节违规 + 边界差异 | 诊断数据 + 边界对比 |
| 假设C | 越界幅度 > 1e-3 rad/m | 诊断数据 + 轨迹分析 |

### 5.3 验收边界

**成功**：
- 3个样本的诊断数据生成完成
- 根因分析报告明确指出属于哪个假设
- 下一轮修复计划的输入条件已满足

**失败**：
- 诊断数据无法生成（输入文件丢失、环境不可用）
- 诊断数据无法确定根因（数据不足、边界一致但仍越界）

**需要扩大范围**：
- 诊断数据显示多种根因混合（需分别处理）
- 需要更多样本验证根因（当前3个不够）

---

## 6. 实际运行前置条件

### 6.1 环境依赖
- [ ] MuJoCo 环境可用（已验证）
- [ ] Python 环境包含所需依赖（numpy, dataclasses-json）
- [ ] 代码库在 commit `025c5389` 或兼容状态

### 6.2 输入文件存在性
- [ ] `development-043003` 原始输入文件（RGB、深度、姿态）
- [ ] `held-out-044009` 原始输入文件
- [ ] `held-out-044011` 原始输入文件
- [ ] 原始 `physical-evidence.json` 可访问（用于对比）

### 6.3 代码库状态
- [ ] `src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py` SHA256: `a0b5891a7075...`
- [ ] `src/cloud_edge_robot_arm/simulation/mujoco/backend.py` SHA256: `498efa2b2947...`（注：问题陈述中的 SHA256 与当前不匹配，需确认版本）
- [ ] `src/cloud_edge_robot_arm/research/freeze_evidence.py` 可修改

### 6.4 存储空间
- [ ] 诊断数据预估 <10MB（3个样本 × 数百步 × 小型JSON）

---

## 7. 风险与约束

### 7.1 可能的失败模式

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 输入文件丢失 | 低 | 高（无法重放） | 提前验证文件存在性，从备份恢复 |
| 重放结果不一致 | 中 | 中（限位步数不同） | 记录差异，分析原因（随机种子、浮点误差） |
| 诊断数据无法确定根因 | 低 | 高（需更多数据） | 扩大样本范围或增加在线日志对比 |
| SHA256 不匹配 | 高 | 中（版本不一致） | 确认当前代码版本，必要时调整验证逻辑 |

### 7.2 对其他功能的影响

- **诊断数据保存**：独立于正常样本，不影响现有评价流程
- **存储开销**：仅在限位违规时保存，正常样本无影响
- **性能开销**：诊断数据提取 <1ms/步，可忽略

### 7.3 存储或性能开销

- 诊断数据：每个违规步 ~2KB（9个关节 × 位置/速度/边界）
- 预估总存储：3个样本 × 平均200违规步 × 2KB = ~1.2MB
- 对评价性能影响：<0.1%（仅在限位时触发）

---

## 8. 决策点

### 8.1 诊断字段实现方式

**决策**：**独立文件**（推荐）

**理由**：
- 不修改 `PhysicalSample` 数据类，避免影响其他功能
- 不增加正常样本的存储开销
- 诊断数据独立于评价结果，便于后续分析和归档

**备选方案**：扩展数据类（如果后续需要诊断字段进入标准评价流程）

---

### 8.2 重放运行范围

**决策**：**完整 episode**

**理由**：
- 确保限位发生的上下文完整（前序轨迹、姿态目标）
- 验证限位步数与原始一致（排除随机性）
- 便于后续分析轨迹可达性（假设C）

**备选方案**：仅运行到限位物理步（如果完整运行时间过长）

---

### 8.3 诊断数据存储位置和格式

**决策**：
- **位置**：`<episode_dir>/component/joint-limit-diagnostics.json`
- **格式**：JSON（结构见第3节）

**理由**：
- 与现有 `physical-evidence.json` 同级，便于关联
- JSON 格式人类可读，便于调试
- 独立文件，不污染现有数据结构

---

### 8.4 如果诊断数据仍不足以确定根因

**决策**：
1. 记录诊断数据不足的具体表现（哪些信息缺失）
2. 生成增强诊断计划（如增加在线日志对比、扩大样本范围）
3. 再次交给 Astra 制定下一轮计划

**不做**：
- 不基于猜测修改代码
- 不跳过根因确认直接尝试修复

---

## 9. 时间估算

| 步骤 | 预估时间 | 累计时间 |
|------|----------|----------|
| 扩展诊断数据保存逻辑 | 1-2小时 | 2小时 |
| 编写重放诊断脚本 | 1小时 | 3小时 |
| 运行3个样本重放 | 30分钟 | 3.5小时 |
| 分析诊断数据 | 1-2小时 | 5小时 |
| 对比在线监测与评价边界 | 1小时 | 6小时 |
| 生成根因报告 | 30分钟 | 6.5小时 |
| 验证与文档 | 1小时 | 7.5小时 |

**总计**：7.5小时（1个工作日）

---

## 10. 输出交付物

1. **诊断数据文件**（3个）：
   - `development-043003/component/joint-limit-diagnostics.json`
   - `held-out-044009/component/joint-limit-diagnostics.json`
   - `held-out-044011/component/joint-limit-diagnostics.json`

2. **根因分析报告**：
   - `artifacts/research/process/20261004-ced-development/astra-rounds/round-joint-limit-diagnosis/root-cause-analysis.md`

3. **诊断脚本**（2个）：
   - `scripts/diagnose_joint_limits.py`
   - `scripts/analyze_joint_limit_diagnostics.py`

4. **代码变更**：
   - `src/cloud_edge_robot_arm/research/freeze_evidence.py`（新增诊断函数）

5. **验证证据**：
   - 诊断数据完整性检查结果
   - 根因分类决策树
   - 下一轮修复计划的输入条件清单

---

## 附录：机器可解析的结构化计划

```json
{
  "plan_id": "round-joint-limit-diagnosis",
  "plan_version": "1.0",
  "created_at": "2026-11-14T17:30:00+08:00",
  "objective": "生成硬限位失败的完整诊断数据，确定根因属于假设A/B/C，为下一轮修复提供输入条件",
  "scope": {
    "in_scope": [
      "生成诊断数据",
      "确定根因",
      "对比在线与评价边界"
    ],
    "out_of_scope": [
      "修复硬限位问题本身",
      "分析其余17项失败",
      "几何判据审查"
    ]
  },
  "input_files": [
    {
      "path": "src/cloud_edge_robot_arm/simulation/mujoco/episode_evaluator.py",
      "sha256": "a0b5891a70752400dcf0dea0cbe837476114148000b9eb345c27fe468860af50",
      "role": "评价核心"
    },
    {
      "path": "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
      "sha256_expected": "d6bf8cc360328187ee7bf6c5b3fb78149b4e4302ee7380e2c4a3fcd7fabae452",
      "sha256_actual": "498efa2b2947d70cce8e311aa57a77fbcb50a978db592f44cba8d0ac2f5aa7e0",
      "role": "后端数据结构",
      "note": "SHA256不匹配，需确认版本差异"
    },
    {
      "path": "/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/geometry-repair-40-20261114-v2/development-043003/component/physical-evidence.json",
      "sha256": "bce0fb30ff4069f4aca355396e62da955f9b44762e7442ab697d885a4bc13de6",
      "role": "样本1逐步证据"
    },
    {
      "path": "/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/geometry-repair-40-20261114-v2/held-out-044009/component/physical-evidence.json",
      "sha256": "f109f755a2d49bff3434316a2287b3454f868e91f9c78e2baffec1b8e288ec16",
      "role": "样本2逐步证据"
    },
    {
      "path": "/home/ningyd/Documents/Codex/2026-11-14/x20-gpu-nvidia-smi-nvml-gpu/outputs/geometry-repair-40-20261114-v2/held-out-044011/component/physical-evidence.json",
      "sha256": "560b76e938fdb8d1876362e16b432981713498116399179a4976ea9770f5857c",
      "role": "样本3逐步证据"
    }
  ],
  "modifications": [
    {
      "file": "src/cloud_edge_robot_arm/research/freeze_evidence.py",
      "type": "extend",
      "changes": ["新增函数 _save_joint_limit_diagnostics()"]
    },
    {
      "file": "scripts/diagnose_joint_limits.py",
      "type": "create",
      "purpose": "重放样本并生成诊断数据"
    },
    {
      "file": "scripts/analyze_joint_limit_diagnostics.py",
      "type": "create",
      "purpose": "分析诊断数据并生成根因报告"
    }
  ],
  "verification_metrics": {
    "diagnostic_file_coverage": {
      "target": "3/3",
      "measurement": "检查文件存在性"
    },
    "field_completeness": {
      "target": "100%",
      "measurement": "验证JSON结构"
    },
    "violated_joint_identification": {
      "target": ">=1 sample",
      "measurement": "检查 violated_joints 非空"
    },
    "joint_data_consistency": {
      "target": "9 joints",
      "measurement": "验证关节位置+手指位置长度"
    }
  },
  "acceptance_criteria": {
    "success": [
      "3个样本的诊断数据生成完成",
      "根因分析报告明确指出属于哪个假设",
      "下一轮修复计划的输入条件已满足"
    ],
    "failure": [
      "诊断数据无法生成（输入文件丢失、环境不可用）",
      "诊断数据无法确定根因（数据不足、边界一致但仍越界）"
    ],
    "expand_scope": [
      "诊断数据显示多种根因混合",
      "需要更多样本验证根因"
    ]
  },
  "hypotheses": [
    {
      "id": "A",
      "description": "越界来自手指关节，在线监测未覆盖",
      "priority": "P2",
      "verification": "诊断数据显示手指关节触发限位 + 在线日志无对应告警"
    },
    {
      "id": "B",
      "description": "机械臂关节映射或边界定义不一致",
      "priority": "P1",
      "verification": "诊断数据显示机械臂关节触发限位 + 在线与评价边界不同"
    },
    {
      "id": "C",
      "description": "控制轨迹本身不可达",
      "priority": "P1",
      "verification": "诊断数据显示大幅越界（>1e-3 rad） + 目标姿态或路径有问题"
    }
  ],
  "prerequisites": {
    "environment": [
      "MuJoCo 环境可用",
      "Python 环境包含 numpy, dataclasses-json"
    ],
    "codebase": [
      "commit 025c5389 或兼容状态",
      "episode_evaluator.py SHA256 匹配",
      "backend.py 版本确认"
    ],
    "data": [
      "development-043003 原始输入文件存在",
      "held-out-044009 原始输入文件存在",
      "held-out-044011 原始输入文件存在"
    ]
  },
  "decisions": {
    "diagnostic_field_implementation": "独立文件（推荐）",
    "replay_scope": "完整 episode",
    "diagnostic_storage_location": "<episode_dir>/component/joint-limit-diagnostics.json",
    "diagnostic_storage_format": "JSON",
    "insufficient_data_fallback": "记录不足表现 → 生成增强诊断计划 → 再次交给 Astra"
  },
  "deliverables": [
    "development-043003/component/joint-limit-diagnostics.json",
    "held-out-044009/component/joint-limit-diagnostics.json",
    "held-out-044011/component/joint-limit-diagnostics.json",
    "artifacts/research/process/20261004-ced-development/astra-rounds/round-joint-limit-diagnosis/root-cause-analysis.md",
    "scripts/diagnose_joint_limits.py",
    "scripts/analyze_joint_limit_diagnostics.py",
    "src/cloud_edge_robot_arm/research/freeze_evidence.py (修改)"
  ],
  "estimated_duration_hours": 7.5
}
```
