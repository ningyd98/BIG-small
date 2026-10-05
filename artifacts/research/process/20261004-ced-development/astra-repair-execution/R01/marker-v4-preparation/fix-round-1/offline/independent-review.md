V4 offline 独审：`PASS_SCOPED_SOFTWARE_AND_READOUT`，无新 qualified 缺陷。仅检查软件与既有终态结果归纳，本独审未重新解码或复算全部 raw。

独立一次17 CPU通过（0.24s）；reader/test Ruff、format、compile全exit0。严格 detector source未变，调用仅接收保存RGB-D和冻结75mm/ID7 registration，不接收truth。reader保留201全分母与raw shape/hash/checksum/context/identity joins，检查完整qpos/qvel/act/ctrl、guard byte domain及nested brackets；固定4806与原120/9/2范围gate沿用已审修复。

既有201行独立统计为201 OBSERVED/0 UNKNOWN，189旧UNKNOWN→OBS、12controls保持OBS，step IDs未迁移。保存corners复算min-side为27/28/30.01666203960727px；201 stability仍UNKNOWN、geometry/velocity bounds为null。report.json与verification完全一致，4807 physical/4806 actuator/743 commands/4807 scorer比较均仅去episode_id且0差异，不声称全部内部状态相同或替换旧pose。

现有output/source pins核对通过，37项限定inputs前后SHA/bytes相同。223raw/54415036B与既有266 before/after inventory元数据相符；本轮未再次打开全部raw做266审计。作者唯一201 decode与本独审decode0分别记录；作者17和独立17不能相加。无actual/model/renderer/reset/physics/provider/hardware调用，只新建本目录三份独审文件，无source/rootdocs/Stage/Git写入。

最大sparse gap实读重算2.1166666836000267s>原0.005s，continuous仍NOT_ESTABLISHED；native/source authority、formal、UTC、future stability及calibration group均不升级。结论只支持另行冻结full-horizon采集的诊断依据。完成后quiet、停止写入。Log SHA：`8a988f0c342595222a341e86370b7a4c67917d88369af853fd54c806ac4a0c26`。
