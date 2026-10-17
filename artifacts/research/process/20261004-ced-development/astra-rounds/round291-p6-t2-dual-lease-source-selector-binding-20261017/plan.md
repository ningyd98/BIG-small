# R291 — bind the dual lease pin to checked current27

Actual gpt-6-astra; plan only. No runtime exception has been observed.

The frozen R289 plan has32 direct inputs and no direct lease entry. The same exact lease pin (40869B/f71d9…) occurs once in checked current27 and matches its complete physical source. The copied consumer still selects from plan.inputs. This is a static source-binding mismatch, not an observed StopIteration.

Permit only the line1128 iterable replacement:

```python
# before
"lease": next(x for x in context["plan"]["inputs"]
# after
"lease": next(x for x in context["before_check"]["sources"]
```

The following exact-path predicate and every other byte remain unchanged. Keep all expected_sources fields and per-pin comparisons, observer/resource predicates, C486 nested completion and protected fail-closed main. ROOT must confirm the lease is unique in the already verified authority and that before_check is established before consumer use.

The originalcc0b candidate/native remain immutable; its fullbytes/base64/mode are preserved here. Sole Sol, only after ROOT acceptance, persists a new R291 candidate with this one substitution, then supplies exact native arguments/actual, limited diff and change report. Expected proposedafter is **96416B/1586lines/SHA693289fe8d54b224e7311f7437fc12201829f9182a3d88c1612723bc07642b1a**; this is calculated, not an implemented pin. Plugin5fd27 remains untouched.

R289 identity/P/Ssupp remain unchanged. After ROOT full candidate/native/input review, the original R289 final two target Adds may proceed from the corrected runner candidate and unchanged plugin. Bind this supplement and its physical evidence in the original sourcegate. No new validator, runtime/static/SQL/Git/review slot, role/context change or execution release. Freeze and STOP for ROOT.
