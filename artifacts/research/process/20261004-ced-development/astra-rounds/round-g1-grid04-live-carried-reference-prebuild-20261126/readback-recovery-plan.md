# 首拒冷读按帧角色比较

gpt-6.2-astra 限定恢复。原独立 read_handoff_live 已成功核验第一份原件。附加比较器在真实 GRASP/POST 的 current 读取 status 时得到 KeyError。POST 由 observe_payload_frame 返回 relation、证据和姿态，而 PRE/FEEDBACK 才用局部净空状态。保留旧脚本 SHA256 8926c89a65c962fb980f42faa3adf1a7bacc5a754798592a24ce8d44c62cd091 与首次通过的冷读。

只改独立比较器。原 PRE/FEEDBACK 比较状态、理由和深度归属。POST 的 status 设为不适用，分别先核验新旧帧身份和已用原角色，再比较 relation、理由与姿态的几何字段。对已封存文件做两份新命名冷读。真实运行、积分、曝光和投影均不追加。
