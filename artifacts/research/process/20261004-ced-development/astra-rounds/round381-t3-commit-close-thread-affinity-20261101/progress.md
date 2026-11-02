# R381 execution

- R389 current HEAD applicability approved; post-R380 hash/review registered, prior paused receipt preserved. Original commit_close hook remains unchanged for real threaded RED. No old long RED rerun.

- Thread RED2 expected failures, original hook hits main-owned SQLite reader on worker thread;1.943s/accepted/clean. Minimal fix uses new observer created/query/closed in current COMMIT hook thread. No flags or SQL semantics changed.

- Thread GREEN2 PASS, real nonterminal/foreign commits cannot fire, true terminal COMMIT closes same writer; observer success/query-error both closed on creating thread, class and module binding restored.

- Shared diagnostic+manifest GREEN6 PASS, accepted/clean. Original commit_close long run starts once under600s cap; source writer locked until complete.

- Original commit_close GREEN1 PASS, outer241.577s, genuine post-COMMIT same-writer closure; public UNCONFIRMED/accepted=false and23 retained files;678 resources/full assertions/restoration/cleanup complete. Context-resume reads terminal receipts, no old budget reset or run retry. Independent review final handoff pending.
