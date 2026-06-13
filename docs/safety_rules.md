# 安全规则文档

## 规则列表

### 1. CMD_EXPIRED（指令过期）
- **检查**：`wall_clock_now > command_valid_until`
- **决策**：REJECT
- **场景**：指令超过有效期

### 2. TEL_FRESH（遥测新鲜度）
- **检查**：遥测时间戳距今 > staleness_ms
- **决策**：PAUSE
- **场景**：遥测数据过期

### 3. SCENE_FRESH（场景新鲜度）
- **检查**：场景更新时间距今 > staleness_ms
- **决策**：PAUSE
- **场景**：场景数据过期

### 4. SCENE_VERSION（场景版本一致性）
- **检查**：`scene_version != expected_scene_version`
- **决策**：REJECT
- **场景**：场景版本不匹配

### 5. CTX_MATCH（上下文匹配）
- **检查**：plan_version、command_seq、step_id 与契约一致
- **决策**：REJECT
- **场景**：上下文信息不一致

### 6. DEV_CONNECTED（设备连接）
- **检查**：`robot_connected == False`
- **决策**：REJECT
- **场景**：机器人未连接

### 7. ESTOP（急停状态）
- **检查**：`robot_estop_engaged == True`
- **决策**：EMERGENCY_STOP
- **场景**：急停已触发

### 8. COLLISION（碰撞检测）
- **检查**：`robot_collision_detected == True`
- **决策**：EMERGENCY_STOP
- **场景**：碰撞已检测到

### 9. WORKSPACE（工作空间边界）
- **检查**：TCP 位置超出工作空间
- **决策**：REJECT
- **适用**：运动技能

### 10. FORBIDDEN（禁入区）
- **检查**：TCP 位于禁入区内
- **决策**：REJECT
- **适用**：运动技能

### 11. REACHABILITY（可达性）
- **检查**：目标距离 > max_reach_m
- **决策**：REJECT
- **适用**：需要目标位姿的技能

### 12. TCP_VEL（TCP 速度）
- **检查**：TCP 速度 > max_tcp_velocity
- **决策**：REJECT
- **适用**：运动技能

### 13. JOINT_VEL（关节速度）
- **检查**：任一关节速度 > max_joint_velocity
- **决策**：REJECT
- **适用**：运动技能

### 14. ACCEL（加速度）
- **检查**：加速度 > max_acceleration
- **决策**：ALLOW（当前为通过检查）
- **适用**：运动技能

### 15. MIN_HEIGHT（最低安全高度）
- **检查**：TCP 高度 < minimum_safe_height
- **决策**：REJECT
- **例外**：APPROACH, GRASP, PLACE, RELEASE

### 16. CARRY_MARGIN（携带安全余量）
- **检查**：携带物体时的额外安全检查
- **决策**：ALLOW
- **适用**：运动技能 + 携带物体

### 17. OBSTACLE（障碍物距离）
- **检查**：TCP 与障碍物距离 < radius + safety_distance
- **决策**：REJECT
- **适用**：运动技能

### 18. PATH_COLLISION（路径碰撞）
- **检查**：碰撞检查开启时的路径检查
- **决策**：ALLOW
- **适用**：运动技能

### 19. STEP_TIMEOUT（步骤超时）
- **检查**：步骤执行时间 > timeout_ms
- **决策**：REJECT

### 20. TASK_DEADLINE（任务截止）
- **检查**：任务截止时间已过
- **决策**：REJECT

### 21. WATCHDOG（Watchdog 超时）
- **检查**：Watchdog 超时
- **决策**：EMERGENCY_STOP
