# R499 Lossless diff-evidence delivery plan

**Planner:** actual gpt-6-astra. **Scope:** artifact delivery only. R498 already passed HTTP200,3.418661s,49/49predicates and finalreview. Its one-request budget is consumed. No API/model/render/test/signal/restart or broad re-review.

## Failure and root cause

The original delivery stopped before commit/push: nested `git diff --cached --check` returned2 (outerdeliveryscript1). Its9warnings point to valid single-space blankcontext lines in newlystaged `runner-adaptation.diff`. This is an evidence-format delivery issue, not product whitespace or failedintegration. CurrentHEAD remainscbb1a2279f47dbf975f22f1a9d5b5b56f1c4e0c4. Read-onlyinspection verified all35selectedpaths exactly staged and stagedblobbytes equal worktreebytes. Exact initialpath/hash evidence is in `initial-staging-evidence.json`.

Originaldiff/candidatedeliverymanifest/failurestdout/stderr are copied byte-identically into draft `original/` for localpreservation; do not stage its raw whitespacebearingfiles. Originalwork/repositorybytes remain untouched. Plans pin originalreceipt/script/source/result/review evidence.

## Narrow correction

1. Verify pins, initial35stagedset andHEAD. Preserve originalcandidate `R498/delivery-manifest.json` unchanged and staged; create exactcopy `R499/original-candidate-delivery-manifest.json`. Do not run old deliver_r498.py again: it assumes an emptyindex/absentreview and can overwrite the originalfailurelogs.
2. Create exact-byte gzip archives with mtime0: R498/runner-adaptation.diff.gz; R499/original-staged-check.stdout.gz; R499/original-staged-check.stderr.gz. Compare decompressedbytes directly with originals and verify both compressed/decompressed size/SHA. Record all mappings in new R499/archive-manifest.json. Never strip whitespace, alter newlinebytes, change Git whitespace rules, or rewrite existingarchives.
3. Unstage **only** R498/runner-adaptation.diff using `git restore --staged -- <exactpath>`; retain raw workingfile unchanged. Leave all other originalstaged entries. Stage the namedcompressed/archive/plan/evidence files via exact NULliteralpathspec; no broadadd/reset. The complete44-path finalallowlist is in plan.json. Optional phase_progress edit is limited to one R499 archiveaudit reference.
4. Write separate R499/final-delivery-manifest.json as authoritative finalinventory: explicitly mark oldR498manifest SUPERSEDED_CANDIDATE; explain rawdiff is represented by lossless .gz. List exact44finalstagedpaths and hash all except the manifestitself with an explicit self-hash exclusion. The originalcandidate is evidence of the failed candidate set, not a claim that rawdiff ships in finalcommit. Preserve both candidatecopies unchanged. Generatefinalmanifest after reports settle; regenerate/re-stage only when a declared finalfile changes.
5. Verify exactstagedset (rawdiff absent), stagedblob/worktree/finalmanifest hashes, allgzip decompressedbytes, originalpins/sourceunchanged, existingsecretscanner over decompressedbytes plus textfiles, and normal `git diff --cached --check` rc0. No checkweakening or repeatintegration. A new work deliveryscript may handle the already-stagedset; preserve oldscript/logs. Commit named artifacts, push existing research/20261004-continuation, and verify local/upstream/remoteSHAequal plus cleanindex. Keep any newcheckfailure/receipt under unique filenames.

## Acceptance

Lossless originaldiff and9-warning evidence preserved; normal stagedcheck passes; exact44paths and explicit finalmanifest authority; product/livebackend unchanged; R498 remains49/49 with no additionalrequest; scopedpushSHAsverified. Newunexpecteddeliveryrootcause returns to Astra. Originalrawresponse stays privatecache and is not added. Planner performed only read-onlyinspection and draftwrites.
