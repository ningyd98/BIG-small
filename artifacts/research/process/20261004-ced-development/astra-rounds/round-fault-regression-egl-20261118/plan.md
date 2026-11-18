# Astra：故障回归EGL前提重跑

实际`gpt-6-astra`，RERUN_PLANNED_NOT_EXECUTED。整份test_visual_servo.py含GL用例，被误当CPU-only；命令漏MUJOCO_GL=egl和共享GPU锁，原栈在renderer.__init__→camera.py43→sensor update→oblique-camera测试206行Abort。原日志31点及其后F不构成完成通过证据；F具体原因尚未解释，不归咎EGL。7项输入SHA见JSON，原件保留。

仅重跑原组，不改产品/测试/断言：从root原工具命令恢复精确selectors（JSON保存用户给的缩写组），先核查已有F详情；等待native_view_repair释放GPU，独占原共享flock全程持锁，以MUJOCO_GL=egl启动原应用Python/pytest，新输出和basetemp、完整-vv/traceback/JUnit/实际argv及exit回执。只运行一次，0模型/API/硬件；已有进度点不追记PASS。新日志如有其它F须逐项读证据交实际Astra再修，重复Abort也不自动重试。不消费真实模型/故障实验额度，不授予正式资格。
