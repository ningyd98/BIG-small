# PPT终稿验证工具环境续计划

实际规划模型：gpt-6-astra；仅计划，未编辑材料、产品或环境。

## 原始失败

父任务原始回执chunk23f57c：finalize.mjs exit1；normalizePresentationFontPolicy内spawnSync bundled Python返回EPERM。stdout包含font_families=[微软雅黑,黑体]且exitCode字段为0，但Node error使finalizer失败。该字段组合不能当作成功。
候选内容据父任务为58处a:t替换；无内容失败证据，亦无版式通过结论。底层原因尚未查明，限定假设为子进程环境/权限问题。

## 前提

- 已有用户修订授权及原轮次计划继续适用；本续计划不批准内容新增。
- 直接命令必须遵守现有沙箱权限；需要权限时走正常require_escalated审批，拒绝后停止受阻步骤，绝不换路径绕过拒绝。
- 同一脚本、同一参数与输入必须可用；检查失败须保留原证据并暂停相关交付，新的根因/范围变化再交实际Astra。
- 如已有原版式缺陷导致检查finding，不能直接放宽规则；保留原/候选对照与差异，按新证据决定是否需下一轮Astra。

## 执行顺序

1. 冻结原失败回执完整文本与脚本、候选hash，执行前重新核对本表全部输入和原轮次原件hash。只读执行路径失败不修改环境库。
2. 通过正常exec_command直接调用同一bundled Python及现有package/layout/font读取脚本，逐项保存argv、stdout、stderr、退出码。保持expected-slide-size-emu=12192000,6858000、validate-bullet-geometry、validate-heading-fit及原参考字体policy；reference源hash、允许字体必须真实核对。
3. 核对finalizer对该候选实际适用的额外只读检查（页数、原生图表/表格及模板等），有适用项同样独立运行并记录；不把略过检查声称为通过。无需改库、删规则或重存候选；独立只读校验不隐含全finalizer等价通过。
4. 通过正常exec_command启动独立Node脚本，沿原runtime_helpers.mjs导入artifact-tool，执行PresentationFile.importPptx(FileBlob.load(candidate))；核对slides.items.length=12、导入前后SHA不变。该脚本直接运行，不调用子进程finalizer，不导出/重写PPT。
5. 父任务继续原计划的非文字包差异核对及逐页渲染视觉检查。保持字体、字号、形状、表格、图像、位置、尺寸；原缺陷与新退化分开记录，不为过检查重设计。
6. 全部适用检查通过且无新版式退化后，逐字复制冻结candidate为最终.pptx，核对final SHA=99aca28b94109b48eb7b66d86d13f3e62a3a544e78a14bdb61547bc58c161513。记录替代调用链及原finalizer失败，不生成虚假的原finalizer成功回执。
7. DOC已成功导出及其独立渲染可继续；输出报告记录本续计划限定环境前提、替代验证结果、限制与原失败。

## 验收边界

- 本轮成功仅指替代只读验证与原格式文件交付；不证明原finalizer已成功、不提升项目运行/正式研究验收。
- PPT12页、候选未被验证工具改写、最终逐字复制及完整hash相等；所有原计划内容/版式验收要求保持。
- EPERM的根因当前只假设为Node子进程环境/权限问题，尚未证明；不由stdout推导权限已解决。
- 若正常直接执行仍失败或权限审批拒绝，保留候选及证据并明确阻塞，未验证文件不冒充完成。

## 本轮冻结输入

| 路径 | SHA256 |
|---|---|
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/plan.md` | `5c99548793c9ac96b4422c21b8b2761746b39795165d14ef45697d3f272cafd7` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/proposal-materials-format-preserving-20261021/plan.json` | `387f6f808c57a9c267a501df837a752295b5c4783808f648aed9fecfeac422a5` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/candidate.pptx` | `99aca28b94109b48eb7b66d86d13f3e62a3a544e78a14bdb61547bc58c161513` |
| `/home/ningyd/文档/ChatGPT/BIGsmall/output/doc/20261021-proposal-revision/.build/pptx-change-map.json` | `6a7558f01822151b1c71dcbbbcf5e7af65482f84673d72c36bfe0f5abcbb81d8` |
| `/tmp/bigsmall-proposal-edit-20261021/finalize.mjs` | `49bc9c4b41d5d84eb6f7b73966fe75191d77429d8bf48837daedaf135e6cc778` |
| `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/artifact_tool_utils.mjs` | `7f3be49b701c385ee180cad5858135297482264039f950d542c22aa9c602645d` |
| `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/inspect_presentation_package_integrity.py` | `0211c115805642094652fb1d464838559b95e4615d15170d22b29d4a23cc9f9f` |
| `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/inspect_presentation_layout_geometry.py` | `171ce664e04705abfef280bf201c7783cfe273747002b2fd04a195b7f447c4eb` |
| `/home/ningyd/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations/container_tools/runtime_helpers.mjs` | `587fb61b967842bddb886be6539c8939ad0828779352bf96a3df2d0ed7c9c227` |

原轮次plan.json的40项冻结输入及全部格式约束继续适用。原失败完整回执由父任务在本目录或原轮次证据目录落盘，计划摘要不能替代原工具回执。
