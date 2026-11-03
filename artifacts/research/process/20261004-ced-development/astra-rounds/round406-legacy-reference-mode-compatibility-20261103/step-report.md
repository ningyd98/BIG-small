# R406 执行记录

104输入与2冻结原件核验一致；仅两处mode比较分阶段替换。新四项真实回归先冻结再RED，原断言/factory/defaultmode/UTClease与原锁修复不改。每阶段独立上限与15秒清理，不复用旧时钟配额。

- legacy_contract_red: FINISHED; exit=1; counts={'passed': 0, 'failed': 1, 'skipped': 0}; 2.782s; expected_accepted=True; reaped=True.

- observation_contract_red: FINISHED; exit=1; counts={'passed': 0, 'failed': 1, 'skipped': 0}; 3.533s; expected_accepted=True; reaped=True.

- legacy_contract_green: FINISHED; exit=0; counts={'passed': 5, 'failed': 0, 'skipped': 0}; 13.518s; expected_accepted=True; reaped=True.

- operational_boundaries_green: FINISHED; exit=0; counts={'passed': 9, 'failed': 0, 'skipped': 0}; 16.176s; expected_accepted=True; reaped=True.

- factory_guards_green: FINISHED; exit=0; counts={'passed': 6, 'failed': 0, 'skipped': 0}; 6.548s; expected_accepted=True; reaped=True.

- 两次预期RED与三组GREEN完成，20项自然通过；R405默认模式前置故障已修，原foreign线程目标自然执行通过。下一轮独立慢writer诊断/当前源权限补验收；原历史状态不回写。
