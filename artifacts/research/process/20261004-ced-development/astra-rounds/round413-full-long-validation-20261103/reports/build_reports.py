"""Render the two requested reports from closed, reconciled evidence only."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

R = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((R / name).read_text())


def cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', '')


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(cell(value) for value in row) + ' |' for row in rows])


def save(name, text):
    with (R / 'reports' / name).open('x', encoding='utf-8') as stream:
        stream.write(text)


def main():
    summary = read('reports/summary.json')
    assert summary['final']
    source = read('postflight/checks.json')
    stages = read('reports/stage-summary.json')
    python = read('reports/python-outcomes.json')
    browser = read('reports/browser-audit.json')
    static = read('reports/static-frontend-audit.json')
    phase12 = read('reports/phase12-audit.json')
    native = read('reports/native-queue-audit.json')
    utc = read('reports/utc-audit.json')
    t3 = read('reports/t3-audit.json')
    start = datetime.fromisoformat(source['batch_started_utc'])
    end = datetime.fromisoformat(source['batch_completed_utc'])
    duration = (end - start).total_seconds()
    local = ZoneInfo('Asia/Shanghai')
    period = f"{start.astimezone(local):%Y-%m-%d %H:%M:%S}—{end.astimezone(local):%Y-%m-%d %H:%M:%S}（北京时间）"
    version = f"被测分支 `research/20261004-continuation`，代码提交 `{summary['tested_commit']}`；官方 real_robot 源码指纹 `{summary['official_source_tree_hash']}`。"
    timing = f"运行区间：{period}；全流程墙钟 {duration:.3f} 秒（{duration / 3600:.3f} 小时）。UTC 起止为 `{source['batch_started_utc']}` / `{source['batch_completed_utc']}`。"
    counts = summary['python_node_counts']
    verification = phase12.get('verification') or {}
    declared = phase12['recomputed_counts']
    phase_status = verification.get('status', 'NOT_AVAILABLE')
    gated = verification.get('verifier_gated_authoritative_thesis_run_count', 'NOT_AVAILABLE')
    categories = [
        ('RUNTIME_SPY_INTERFACE_DRIFT', '测试替身接口不一致', 'RuntimeSpy缺少_local_mode，21项在check_active处失败，目标capture/plan/supervision断言未得到有效验证。'),
        ('RECAPTURE_CALLBACK_SIGNATURE_DRIFT', '回调签名不一致', 'post安全门场景的recapture测试lambda不接受completion关键字，不能据此宣称实际安全门已验证。'),
        ('LEASE_HANDOFF_CONCURRENCY_OR_AUTHORITY', '租约交接并发/授权', '3项嵌套public mutation授权拒绝、1项database is locked、1项跨进程Queue.Empty；产品与测试注入前置的根因尚待分离。'),
        ('PHASE12_RECEIPT_AND_ACCEPTANCE_CONTRACT', '运行回执与验收契约', 'F20计数应1实际0；另一项期望accepted实际evidence-gaps。内层BLOCKED_BY_ENV而外层宣称SUCCESS需要优先处理。'),
        ('EVENT_TRACE_REPRODUCIBILITY', '事件轨迹复现性', '两项相同配置/seed的result_hash比较通过，事件摘要或payload_hash不一致；具体差异字段未通过额外重跑定位。'),
        ('CHINESE_DOCSTRINGS_AND_AUDIT_SCOPE', '中文规范与覆盖', '29+9+2个公共文档字符串缺口，及2330个tracked代码路径未纳入默认审计；这是被测ab18基线下的计数。')]
    category_table = table(['类别', '失败数', '证据解释'],
                           [(label, python['failure_category_counts'].get(key, 0), explanation)
                            for key, label, explanation in categories])
    native_table = table(['开发运行', '终态', '耗时/秒', 'attempt'],
                         [(run['run_id'], run['status'], f"{run['elapsed_s']:.6f}", run['attempts']) for run in native['runs']])
    result_table = table(['范围', '本轮结果', '含义'], [
        ('Python采集', '4753唯一节点 / 288模块 / 0采集错误', '比旧4732清单增加21项，未丢旧节点'),
        ('软件节点', f"{counts.get('PASSED', 0)} PASS / {counts.get('FAILED', 0)} FAIL / {counts.get('SKIPPED', 0)} SKIP / {counts.get('INCOMPLETE', 0)} INCOMPLETE", '4751项均STARTED一次；不以未完成或skip冒充通过'),
        ('真实数据节点', '2 NOT_RUN_EXTERNAL_DATA', 'robomind / graspclutter6d实际数据未运行'),
        ('关键闭环', '94 PASS，另9项关键回归PASS', '9个T3长节点+85闭环节点；关键9项含native队列与模式兼容'),
        ('浏览器', f"{browser['counts'].get('PASSED', 0)} PASS / {browser['counts'].get('SKIPPED', 0)} 原有SKIP", f"旧19项全部PASS；cleanup={browser['cleanup_confirmed']}"),
        ('前端开发', 'Vitest43 PASS；app/node类型、ESLint、构建PASS', 'Prettier与API生成一致性检查FAIL'),
        ('Phase12 full', f"{declared['run_count']}结果行；verifier={phase_status}", '登记行、raw声明、内层真实回执、正式验收分别统计')])
    development = f'''# R413 全量长测后的研发进展

本轮完成一次全量诊断执行，整体尚未达到全部通过或正式研究封板条件。ETEAC不结束问题已有当前代码的原生MOCK队列回归证据；新暴露的测试接口不一致、租约交接、回执真实性和事件复现问题继续保留。

{version}

{timing}

## 当前可确认的研发交付

SQLite持锁内部读取路径修复后，ETEAC与排队PCSC都能自然结束。下列运行各attempt=1，租约释放，结束后心跳线程与运行DB句柄列表均为空。这是开发用原生MOCK证据；不能升级成实体机器人验收。

{native_table}

UTC默认模式已进入原typed validator，未知模式拒绝以及owner/thread/source/clock约束继续保留。Memory与SQLite两项UTC长场景均通过，T3完整9项通过，之前5个失败目标在本轮全部执行并通过。关键闭环合计94项通过。

UTC性能仍未达标：Memory {utc['cases'][0]['stage_elapsed_s']:.3f}秒，SQLite {utc['cases'][1]['stage_elapsed_s']:.3f}秒，合计{utc['combined_stage_elapsed_s']:.3f}秒；原合计600秒门槛未满足。诊断每项7200秒额度不替代原性能门槛，也不代表生产请求延迟。

浏览器本轮42项通过、1项原有跳过，旧19项失败逐项恢复；研究页面/导出展示契约通过，仍明确为600组、4200项全部blocked、actual research NOT_RUN、formal=false。前端单测43项和构建通过，但API新增publication/confirmed_succeeded等发布确认字段尚未同步到仓库生成契约。

{result_table}

## 当前问题及优先次序

{category_table}

1. 先恢复21项RuntimeSpy接口与1项recapture回调的真实测试前置，保留现有source/lease/clock拒绝规则，使目标位置得到验证。租约组5项需要单独分清并发实现与测试注入契约，不能直接放宽授权或替换锁使检查通过。
2. 修正Phase11适配器的输入模式与内层终态传播。已保留的新鲜回执显示：draft省略input_mode而默认走RGBD，MOCK报RGBD_CAMERA_REQUIRED，main/recovery/duplicate均BLOCKED_BY_ENV；外层仍声称SUCCESS、runtime_completed及task_success。F20断言计数0而非1直接暴露该问题。必须先保证结果真实性，再解释成功率或论文样本。
3. 定位两项seed事件复现失败，以及UTC两后端合计4502.509秒的性能瓶颈。本轮没有追加重跑、profile或放宽阈值；具体复现差异字段与耗时根因尚未确证。
4. 处理静态与契约缺口：Ruff {static['ruff_diagnostic_count']}条（{static['ruff_file_count']}文件），format {static['ruff_format_would_reformat']}文件，Prettier {len(static['prettier_files'])}文件，文档检查{static['docs_failure_count']}条规则命中。Mypy本次因缺py.typed直接exit2，没有形成有效源码类型检查结果；不能称类型检查完成。文档敏感内容规则命中未经逐条证实，不直接等同泄露。

## 全量实验与正式研究边界

Phase12 full固定矩阵预期5580行，本轮落盘{declared['run_count']}行。raw声明adapter_attempt={declared['adapter_attempt_count']}、runtime_invocation={declared['runtime_invocation_count']}、runtime_completion={declared['runtime_completion_count']}、BLOCKED_BY_ENV={declared['blocked_by_env_count']}；这些字段不等于成功任务数。内层回执审计中Phase11不支持外层完成声明的行数为{phase12['phase11_unsupported_claims']}，其中F20为{phase12['f20_unsupported_claims']}。最终verifier `{phase_status}`，门控后的论文权威行数为{gated}。详见测试报告及phase12-audit.json，不能使用raw SUCCESS数量替代正式验收。

本轮未完成真实外部数据、真实模型/Isaac/ROS/实体控制器及正式CED资格、校准、B0/INITIAL/METHOD/FINAL验收。云端沿用用户选定方案，边缘模型选型后置，端侧OpenCV及可见姿态标记、顶视相机、控制器方案均保持。

## 来源、历史与交付

R414在工作台7项首次启动前移除共享SIMDB覆盖，同序7PASS；R415修正新续跑器嵌套资源目录准备，只接续可信从未STARTED节点。原075的2项失败和1项未完成保留，原073/076两个管理阻断均为零行为，不加入测试分母。产品与测试字节未改，旧raw、partial目录、两个dirty gitlinks保留；不称整个工作区干净。

旧R407采样子进程精确退出原因仍UNKNOWN，本轮不能反推其原因。原生回执沿用的patched_worktree=true等历史标签不改写，当前来源以实际HEAD与源pin为准。docs/current_authoritative_status.md仍是11月2日快照，其ETEAC/旧19浏览器待办不能替代本轮结果。

这份报告对应被测ab18代码。后续交付提交仅新增精选证据与报告；新增tracked路径会影响治理审计输入，未宣称对交付提交重新执行整套长测。完整raw、运行DB、缓存、凭据、模型、SDK及大图像/trace留在本地；精选清单不等于完整远端复现包。最终review与Git三处SHA回执在本轮review/delivery目录另存。

配套：[测试报告](test-report.md)、[唯一覆盖总账](coverage-ledger.json)、[Python失败分类](python-outcomes.json)、[全量实验审计](phase12-audit.json)、[来源与清理核验](../postflight/checks.json)。
'''
    save('development-progress.md', development)
    # The detailed test report is built below from the same closed inputs.
    build_test_report(summary, source, stages, python, browser, static, phase12, utc, t3,
                      version, timing, result_table, category_table, native_table)
    step = f'''# R413 全量长测步骤报告

{version}

{timing}

实际gpt-6-astra的R413计划先于采集/运行，R414数据库前置与R415资源父目录前置均先取得独立Astra限定计划，再实施。三轮计划与冻结输入SHA保留；本轮没有产品或测试修复。

一次新采集4753唯一节点/288模块，软件4751节点各STARTED一次。最终4709PASS、35FAIL、6原backend SKIP、1INCOMPLETE，2真实数据NOT_RUN另列；全局重复STARTED=0。前后源pin和tracked开发源码一致。关键9回归及94闭环通过，UTC性能600秒合计门槛未满足。全部原失败、缺失JUnit与原075预算终止不覆盖。

R414在073零行为时管理阻断旧父，7项新scope完整PASS；R415在旧075已TIMEOUT且旧tail尚未invoked的真实目录错误后，只续38个可信未STARTED节点。原076guard为零行为，后继同4项原序。两管理slot与测试尝试分开。

非Python22步骤的实际terminal、退出码与原始日志全部汇入测试报告。浏览器42PASS+1原有SKIP，旧19项全部PASS；前端Vitest43PASS。7个静态/前端检查未通过或未进入有效类型检查。Phase12预期5580行，实际{declared['run_count']}行，最终verifier={phase_status}，门控论文权威行={gated}；raw完成声明与内层支持单独审计。

开发验证、真实软件/仿真执行、正式研究/硬件验收分别记载。完整raw/DB留本地；精选交付不冒充完整远端复现包。测试代码基线为ab18，后续Git证据提交与fresh review/远端SHA回执独立保存。

完整结果：[研发进展](reports/development-progress.md)、[测试报告](reports/test-report.md)、[最终来源核验](postflight/checks.json)。
'''
    with (R / 'phase-step-report.md').open('x', encoding='utf-8') as stream:
        stream.write(step)
    with (R / 'phase-summary.md').open('x', encoding='utf-8') as stream:
        stream.write('# R413—R415 阶段总结\n\n' +
                     '全量诊断与本地报告收口，整体未全绿，正式研究未封板。ETEAC队列可结束及UTC语义闭环取得当前来源回归证据；' +
                     '21项Spy接口、1项回调接口、5项租约交接、2项回执/验收、2项事件复现、4项中文规范仍为失败，另有1项预算未完成。' +
                     'UTC性能、7个静态/前端门槛及外部研究证据缺口保持。\n\n' +
                     f'Phase12 raw行={declared["run_count"]}，verifier={phase_status}，门控论文权威行={gated}。' +
                     '后续产品或输入修复须按新根因先取得实际Astra计划；不放宽门槛、清理旧失败或改实验原字节。\n\n' +
                     '[研发进展](reports/development-progress.md) · [测试报告](reports/test-report.md) · [步骤报告](phase-step-report.md)\n')


def build_test_report(summary, source, stages, python, browser, static, phase12, utc, t3,
                      version, timing, result_table, category_table, native_table):
    t3_table = table(['阶段', '原节点', 'call/秒', '阶段/秒', '结果'],
                     [(row['stage_id'], row['nodeid'], f"{row['call_duration_s']:.6f}",
                       f"{row['elapsed_s']:.6f}", 'PASS') for row in t3['stages']])
    failures = []
    for number, row in enumerate(python['failed_tests'], 1):
        excerpt = row['first_failure_evidence'].splitlines()
        excerpt = ' / '.join(excerpt[-4:])[:450]
        failures.append((number, '`' + row['nodeid'] + '`', row['category'], excerpt,
                         ', '.join(row['stage_ids'])))
    failure_table = table(['序号', '节点', '分类', '原失败摘要', '阶段'], failures)
    skip_table = table(['节点', '原skip原因'],
                       [(row['nodeid'], row['details'][0]['longrepr']) for row in python['skips']])
    other = [row for row in stages if row['expected_nodes'] == 0]
    stage_table = table(['阶段', '状态', 'exit', '耗时/秒', 'JUnit'],
                        [(row['id'], row['status'], (row['result'] or {}).get('returncode'),
                          f"{(row['result'] or {}).get('elapsed_s', 0):.6f}" if (row['result'] or {}).get('elapsed_s') is not None else 'N/A',
                          json.dumps(row['junit'].get('counts', {}), ensure_ascii=False)) for row in other])
    matrix = table(['实验', '预期行', '实有行', 'raw状态', 'raw调用/完成声明'],
                   [(row['experiment_id'], row['expected_result_rows'], row['actual_result_rows'],
                     json.dumps(row['status_counts'], ensure_ascii=False),
                     f"{row['runtime_invocations']} / {row['runtime_completions']}") for row in phase12['experiments']])
    verification = phase12.get('verification') or {}
    declared = phase12['recomputed_counts']
    failed_checks = '\n'.join('- `' + name + '`' for name in phase12['verification_failed_checks']) or '- 无可列出的失败检查；不据此推断缺失验收文件已通过。'
    issues = '\n'.join('- `' + item['issue'] + '`：' +
                       cell({key: value for key, value in item.items() if key not in ['issue', 'run_ids']})
                       for item in phase12['issues']) or '- 离线结构/计数审计未发现额外问题。'
    nonpython_fail = [row['id'] for row in other if row['status'] == 'FAILED']
    missing_junit = summary['python_started'] - summary['junit_confirmed_python_nodes']
    report = f'''# R413 全量长测测试报告

执行收口，整体未全部通过；不能据此宣布正式研究验收通过。报告包含失败、跳过、未完成和外部未运行项，没有以软件通过替代真实实验。

{version}

{timing}

## 1. 范围与方法

一次新采集得到4753个唯一节点、288个模块，collection error=0；4751软件节点与2个真实数据节点分开登记。相对旧4732清单增加21项，旧节点未丢失。软件节点按关键长node及其余模块隔离进程执行，不能等同于单一pytest进程的全套共享状态运行。

所有4751软件节点STARTED各一次，重复启动0。只有事件明确未开始的节点才允许尾部接续；已开始且未完成者不重跑。原始测试顺序、断言、产品TTL/timeout/并发策略、模型与硬件门禁保留。默认模块1800秒，可信未开始尾部每项600秒；UTC每后端7200秒；其它长节点与闭环按各自冻结spec额度执行；浏览器默认600/研究300秒；Phase12 full14400秒、后续每阶段1800秒，owned清理上限30秒。额度是上限，不是性能验收线或等待时长预测。

{result_table}

JUnit确认{summary['junit_confirmed_python_nodes']}个Python节点。原075被1800秒预算终止，{missing_junit}个已开始节点没有该模块的JUnit终态文件：其中11项三阶段PASS、2项call FAIL、1项INCOMPLETE。完整阶段事件、真实exit、source和清理记录仍在；不能补造JUnit或把原模块写成整组PASS。6项backend参数化skip是原测试行为，2项外部数据NOT_RUN不是skip。详情见[唯一覆盖总账](coverage-ledger.json)及[Python收口记录](python-outcomes.json)。

## 2. 关键闭环与长节点

原生开发MOCK队列5项与默认模式兼容4项通过，另94项闭环全部通过；它们均已包含在4751分母内，不额外加总。原生队列运行如下，结束后租约释放、heartbeat线程与run SQLite FD均无残留：

{native_table}

完整T3九项均三阶段PASS、source一致、owned回收；原五个失败目标全部执行到断言并通过：

{t3_table}

UTC两后端合计{utc['combined_stage_elapsed_s']:.6f}秒，原合计600秒性能门槛**未达到**。测试使用局部UTC跳变±一天和late-return拒绝场景，没有调整宿主时钟。耗时包含该测试自身观测逻辑与共享主机条件，不直接等同生产延迟；本轮没有追加profile来确证性能归因。9项T3阶段合计{t3['combined_stage_elapsed_s']:.6f}秒。[UTC核验](utc-audit.json)、[T3核验](t3-audit.json)、[原生队列核验](native-queue-audit.json)保留精确证据SHA。

## 3. 软件失败与验证空缺

{category_table}

RuntimeSpy的21项与recapture的1项属于已观测到的测试接口不匹配：失败发生在目标检查前，不能作为目标行为已经验证、或21个生产缺陷的证明。租约组5项则仍需区分测试注入契约与真实并发实现；本轮不通过放宽嵌套写入授权、替换锁或改断言来消除失败。

F20新鲜证据显示，默认RGBD使MOCK任务报RGBD_CAMERA_REQUIRED、task_execution=NOT_RUN、内层BLOCKED_BY_ENV，外层适配器却声称成功。证据和静态源码链见[f20-receipt-audit.json](f20-receipt-audit.json)以及[evidence/f20-first-duplicate-result.json](evidence/f20-first-duplicate-result.json)。这是回执真实性缺口；不是新增一次修复后的GREEN运行。旧R373对应F20节点是NOT_COMPLETED，不能称本轮从旧PASS回归。

两项复现性失败的result_hash比较通过，但过滤后的event digest或payload_hash序列不同；完整差异payload没有由原测试导出为JSON。本轮未为补证再次运行或额外打开其运行SQLite。已保留现有失败及本地DB文件SHA，根因尚未确定。

35项失败逐项如下；完整longrepr、三阶段耗时及原日志位置保存在总账/Python收口记录，表中只截取首个失败证据摘要：

{failure_table}

唯一INCOMPLETE节点为 `tests/test_phase12_2_runtime_authenticity.py::test_verifier_rejects_runtime_gap_when_runtime_receipt_missing`。它已STARTED，故没有进入38个未启动尾部的接续队列；本轮没有取得其call/teardown终态。

六项原有backend参数化跳过：

{skip_table}

两个真实数据节点：`tests/test_external_rgbd_real.py::test_actual_loader_and_offline_provider[robomind]` 与 `[graspclutter6d]`，均为NOT_RUN_EXTERNAL_DATA；未下载数据或以fixture代替实际数据验收。

## 4. 静态、前端、浏览器与实验步骤

共22个非Python步骤；该表使用原阶段returncode与terminal，不把controller循环正常结束误写成所有检查通过：

{stage_table}

非Python失败阶段：{', '.join(nonpython_fail)}。

- Ruff check：{static['ruff_diagnostic_count']}条诊断、{static['ruff_file_count']}文件；按代码分布 `{json.dumps(static['ruff_by_code'], ensure_ascii=False)}`。包含B023/B905等潜在逻辑规则，不全是格式。旧R410仅四文件的40项基线不能代表本次全范围；本轮未引入源码改动。
- Ruff format：{static['ruff_format_would_reformat']}文件需格式化，原输出 `{static['ruff_format_summary']}`；Prettier {len(static['prettier_files'])}文件。
- 中文CLI：342条MISSING标记；pytest另暴露40个公共文档字符串缺口及2330个tracked路径覆盖缺口，三者计量口径不同。
- 文档规则：{static['docs_failure_count']}条，`{json.dumps(static['docs_failure_by_check'], ensure_ascii=False)}`。规则命中未经逐项裁定为实际敏感值泄露或真实引用损坏；原详细扫描保留本地，精选审计只保存脱敏分类。
- Mypy：实际命令为 `python -m mypy --cache-dir <fresh> -p cloud_edge_robot_arm`，exit2，提示缺少py.typed；仓库CI入口是 `python -m mypy .`。本次没有形成有效源码类型检查结果，也没有追加改入口重跑；不能把exit2解释为源码类型错误数量。
- API导出：原OpenAPI与生成JSON解析后也不等价，TS生成文件同样不同。差异包括PublicationStatusView、AttemptView/SimulationRunRecord等publication字段、BatchProgress.confirmed_succeeded/unconfirmed_terminal、BatchRecord.publication_state和TimelineEvent.historical_payload。生成、typegen、Prettier三个原步骤均在新输出目录完成，原仓库生成文件未被覆盖。

前端单测43PASS，app/node类型检查、ESLint、构建PASS；这些通过不替代生成契约一致性检查。详见[静态与前端审计](static-frontend-audit.json)。

浏览器默认39PASS+1原有SKIP、research 3PASS；合计42PASS+1SKIP。旧19项按classname+name逐项比较，19项全部PASS，额外skip=0；原有E2E06因PLAYWRIGHT_MUJOCO_RUNTIME=0保留，缺失duration保持null。两suite使用新DB、workers=1、retries=0、reuseExistingServer=false，断言及原等待不放宽；结束后默认8000/5173与research8123/5199端口可用、owned子树回收。MuJoCo/EGL图像仿真不等同实体机器人。

研究页面观测：scope=SOFTWARE_ONLY、groups=600、assigned=4200、blocked=4200、actual_research_status=NOT_RUN、formal_accepted=false，导出与页面一致。这是展示/导出契约，不是4200项真实研究成功。[浏览器逐项核验](browser-audit.json)。

## 5. Phase12 full矩阵与真实性审计

预期20个实验、5580登记结果行；实有manifest={phase12['manifest_count']}、raw={declared['run_count']}、unique run_id={phase12['unique_run_ids']}。矩阵计量以scenario×backend×mode×seed×repetition展开；F20的policy task_count=100不能据180行就宣称完成18000个实际任务。

{matrix}

raw声明：adapter尝试{declared['adapter_attempt_count']}、runtime调用{declared['runtime_invocation_count']}、runtime完成{declared['runtime_completion_count']}、environment阻塞{declared['blocked_by_env_count']}、阻塞前未调用runtime {declared['blocked_before_runtime_count']}、synthetic pipeline样本{declared['synthetic_sample_count']}、raw-declared authoritative={declared['authoritative_thesis_run_count']}。这些是原始字段聚合，不能直接解释成有效完成任务或正式权威样本。

独立检查Phase11内层main/duplicate/recovery回执后，不支持外层完成声明的行数{phase12['phase11_unsupported_claims']}；其中F20为{phase12['f20_unsupported_claims']}，支持F20声明的回执仅{phase12['f20_receipts_supporting_claim']}。内层状态与外层SUCCESS矛盾保持，不修改raw或用清单代替native证据。

最终verifier原值：status=`{verification.get('status', 'NOT_AVAILABLE')}`；thesis_status=`{verification.get('thesis_status', 'NOT_AVAILABLE')}`；full_profile_execution_status=`{verification.get('full_profile_execution_status', 'NOT_AVAILABLE')}`；project_status=`{verification.get('project_status', 'NOT_AVAILABLE')}`；verifier-gated authoritative rows=`{verification.get('verifier_gated_authoritative_thesis_run_count', 'NOT_AVAILABLE')}`。退出码0的run/analyze/export只说明相应程序结束，不能替代verifier或真实研究验收。

verifier未通过的检查：

{failed_checks}

离线结构/计数/内层回执审计事项：

{issues}

ISAAC_SIM_ROOT与ROS_DISTRO未注入子环境，外部planner adapter固定BLOCKED_BY_ENV；verify的skip flags只是输出字段，不是run阶段安全门禁。本轮不触发外部模型/实体硬件。环境前置NVIDIA字段含driver错误文本，预探测在受限上下文运行，不能把非空文本或本轮EGL通过升级为全主机GPU/Isaac已验收。各字段与原始文件SHA见[phase12-audit.json](phase12-audit.json)。

## 6. 两次前置交接、来源与资源边界

R414实际Astra计划在原073未启动时追加launched=false、attempts=0管理guard。原parent自然在Popen前拒绝，session12273实际exit1，属于预期管理交接；同7节点新scope只移除SIMULATION_RUNTIME_DB覆盖，完整7PASS、15.548432秒。6份实际DB分别位于各test/artifacts，未产生stage共享DB；旧字节不改。

R415实际Astra先静态定位原尾部mkdir缺少parents问题。原075随后正常耗尽1800秒额度，source一致、SIGTERM后root/child回收；交接没有主动发送信号。旧parent在首个tail的r223/resources准备处实际FileNotFoundError，尚未invoked该tail；原partial目录保留。原076管理guard未启动也未触发拒绝。新runner复用原run_one/bounded_stage，派生execute仅修资源子目录parents/exist_ok与tail namespace，AST反向归一化和compile核验；只接续38个从未STARTED节点并继续剩余队列。原075失败/未完成与两处零行为管理slot不重复计数。[R414步骤](../../round414-workbench-db-scope-preflight-handoff-20261103/handoff-step-report.md)、[R415步骤](../../round415-unstarted-tail-resource-parent-handoff-20261103/handoff-step-report.md)。

最终全部{source['runtime_pin_count']}份运行来源pin相等，tracked开发源码diff为空，Git HEAD仍为被测ab18；main与两处gitlink的外层index SHA未变，未进入dirty gitlink目录。经批准主机/proc核验已观察owned身份{source['observed_owned_identities']}个，最终存活0；Python前置记录{len(source['python_prerequisite_records'])}份均accepted。官方real_robot源指纹、NUL规范化清单hash、Phase12 provenance源hash采用不同算法，不能因digest不同就断言同源冲突。详见[最终来源/清理](../postflight/checks.json)。

资源采样实际为每20秒读取owned进程CPU ticks/RSS；计划中周期cgroup采样没有实现，这是观测范围偏差。没有据此断言OOM、生产资源峰值或旧R407退出原因；旧R407精确exit仍UNKNOWN。原生回执保留的patched_worktree=true/旧字段名属于继承标签，以当前实际HEAD与pin核对来源，不改写原件使其好看。

完整raw、运行DB/WAL/SHM、外置/tmp、fixtures重复副本、images/traces、缓存、凭据、模型和SDK不进入精选Git包。交付manifest记录选择与边界，不能冒充完整远端复现包。全部开发验证、真实软件/仿真调用、正式研究/实体硬件验收分开；本轮formal_accepted=false。Git交付与fresh whole-evidence review在本轮delivery/review下独立记录，不以失败消失作为报告交付条件。
'''
    save('test-report.md', report)


if __name__ == '__main__':
    main()
