# R332 source dependency correction

Actual Astra planned the correction; the existing GPT-6.1-sol author inserted the exact inherited `sha` definition and its one provenance entry. ROOT independently reconstructed every pre-existing helper byte, checked unchanged provenance, and recursively checked symbol-table dependencies. No unresolved global remains.

`root-acceptance-reconciled.json` accepts this static repair only. The earlier `root-acceptance.json` is retained: ROOT initially compared an AST segment without its trailing newline against the established complete-source-line hash. Reconciliation used the existing line convention; no implementation or provenance correction was needed.

Original helper, finding, plan, minimal diff and author proof remain preserved. R331 RED/GREEN remain unused and held. This is not a test pass, T3 completion, final B acceptance or physical/research evidence. R333 and R334 are separate appended-test source findings.
