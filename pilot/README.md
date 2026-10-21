# Pilot: simulating a repo's future requirements

Goal: test whether we can (a) predict how a repo will need to change, and (b) score code on whether it survives those changes, using real repos whose future the model hasn't seen.

**Setup.** Pick repos with commits after the model's knowledge cutoff (June 2026). Snapshot each at 2026-06-01. The "future" is everything merged since, up to 2026-10-15.

## Results

| Repo | Today's tests on May code | What the failures are |
|---|---|---|
| tinydb (small, maintenance mode) | 9 of 228 fail | 7 latent edge-case bugs in existing code |
| click (large, active) | 249 failed + 3 collection errors, of ~3,100 | Mostly new features and deliberate behaviour changes (PowerShell completion, `Parameter.spec`, help changes, color validation), plus some bug fixes |

- **Prediction (tinydb, done blind):** 7 of 11 predictions hit at least partially, but mostly the generic ones (release, typing, docs, deps). Only 1 of 8 real code fixes was predicted outright. Details are in `tinydb/`.
- **Future tests make a clean, cheap reward.** Run the repo's later tests against code written at the snapshot. This needs no LLM judge and no synthetic data, and it worked on both repos with one script.
- **Blind hardening run (tinydb):** a fresh agent given only the May code fixed 20 suspected bugs. Future tests failing dropped from **9 to 5, with 0 regressions**. It anticipated 4 of the 8 real later bug reports outright and 1 partly, against 1 of 8 for roadmap-style prediction. Details: `tinydb/3-blind-hardening.md`.
- **Scale-up (8 repos, 3 runs each, plus 8 audited sandboxed runs):** blind hardening fixed 26% of target future tests pooled with 3 regressions in 24 runs. On bug-fix tests only, recall is 32% pooled (25% per-repo mean); none of the 49 new-feature tests was ever fixed. The sandboxed round matched round 1 on 7 of 8 repos. Details: `scale-up/README.md`.
- **Misses and precision:** of 116 real future bugs, 39% were caught by at least one of 32 runs; agents do well on state/caching bugs and poorly on output fidelity, domain rules, degenerate inputs and performance. Of 134 fixes in the sandboxed runs, 84% are real bugs (tests verified against the snapshot), and 56% are real bugs upstream still hasn't fixed. Details: `analysis/README.md`.
- **Prompt A/B test (4 held-out repos, 2 runs per arm):** adding a "how to search" block built from the miss analysis raised distinct future bugs caught from 15 to 21 of 60 run-bug pairs (union 9 to 13 of 30), with 0 regressions in either arm. The gain is mostly python-dotenv, the least blind repo; on the two clean repos it was 6 to 9. Details: `ab-test/README.md`.
- **Two kinds of "future" need separating.** Latent bugs (tinydb) reward robust code. Feature additions and intentional API changes (most of click) can't be anticipated from the code, so they mostly measure how easy the code is to change. A reward should split these, for example by keeping only future tests that exercise APIs that existed at the snapshot.

## Files

- `future_tests.sh`: reusable harness. `future_tests.sh <owner/repo> <cutoff> <package path> <tests dir>`. Set `INSTALL=1` for src/ layouts and use `PYTEST_ARGS` to skip slow files (click needed `--ignore=tests/test_stream_lifecycle.py --continue-on-collection-errors`).
- `tinydb/1-predictions.md`: blind predictions, written before the future was read.
- `tinydb/2-what-shipped-and-score.md`: what shipped and how the predictions scored.
- `tinydb/3-blind-hardening.md` and `tinydb/blind-hardening.patch`: the blind hardening run and its diff.

## Caveats

- One predictor run (this session's model), one small repo for prediction. It's a demonstration, not a measurement.
- Leakage is controlled only by the cutoff date. Snapshot code and tests before June 2026 may be in training data, but the future changes aren't.
- The click prediction step wasn't done blind, so only its harness numbers are reported.

## Next steps

- ~~Repeat the blind run on 5 to 10 repos~~ Done, including bug/feature labels and an audited sandboxed rerun; see `scale-up/README.md`.
- Filter click-style feature tests down to APIs that existed at the snapshot, so larger repos can be scored the same way.
- Turn it into an RL environment. The reward is future tests fixed, minus regressions, minus a churn penalty.
