# 已封存相机预检读回修复

基线 004f9c837ce10fea4a3db6097c3f9abb5909d139。原分配调用退出1、0留出试次、0注册episode。名义真实零步预检 supported=true；right 实际 ValueError 为 initial registered observation unavailable: camera_orientation_not_supported，适配器只匹配 initial registered geometry unavailable: camera_orientation_not_supported。两处原产品抛出点相同原因，均代表拒绝此相机。私有原件及源码/测试快照见 SHA 表。

仅改 proposal_closed_loop.py、对应专项测试与运行清单。先核对所有 SHA 和零步、零派发、相机测量、原帧与登记绑定、名义阳性及 right 阴性；保留原失败与缓存文件。新分配读回已封存探针，禁止重新探针。仅准入原 observation/geometry 两条完整拒绝消息及对应源，且 right 必须仅在已绑定原件上退到名义。缓存路径、SHA、frame绑定、机位、失败原因、源或已占用状态不符全部拒绝。用封存证据复现原 RED，另测未知前缀、错SHA及名义拒绝。复用原计划四个不变摆放、原种子与零重试，仅名义机位；用新独占输出签发、执行、评分，旧目录只读。写明被拒机位、单臂分母4及相机未构成在线对照。独立校验输出，不修改产品、正式身份或原门限。
