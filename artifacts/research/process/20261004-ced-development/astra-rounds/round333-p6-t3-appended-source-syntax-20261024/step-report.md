# R333 appended-source syntax correction

The actual source-only AST failure and original command/traceback are preserved. Actual Astra restricted repair to twelve ASCII spaces at line 5785. The same GPT-6.1-sol author made that exact insertion; ROOT independently reconstructed the full after bytes, checked the original 260206-byte prefix, parsed the complete source, built its symbol table, and verified the return belongs to the nested `after()` callback.

`root-acceptance.json` accepts only this source-syntax repair. Product sources, plans, runner and runtime ledgers remain unchanged. No module import, test collection or runtime occurred; R331 RED/GREEN remain unused and held.

The separate UTC fixture binding finding is recorded under R334 and must receive its own actual Astra disposition before repair. No T3 or final B behavioral acceptance is claimed.
