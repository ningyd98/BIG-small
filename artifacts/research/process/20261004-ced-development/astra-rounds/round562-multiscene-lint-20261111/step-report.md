# R562 静态修正步骤

严格两处修改，冻结源码gzip、原Ruff输出及actual-edit.diff.gz保留。只将唯一case-error lambda中的exc按既有同对象别名error归一化后，全模块AST等价；f字符串排版保持JoinedStr。其后R563独立完成已批准的两个验证函数变更，全部85项harness包含于最终317项组合GREEN，scopedRuff/diff通过。R562没有业务、生产、模型或预算修改，实际调用0。
