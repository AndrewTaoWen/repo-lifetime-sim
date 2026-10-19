# tinydb: blind hardening run

A fresh agent got only the May 2026 snapshot (no network, no git history, no access to the future). It was asked to find and fix latent bugs while keeping the public API unchanged. It fixed 20 suspected bugs, added 24 regression tests, and kept all 216 existing tests passing. Patch: `blind-hardening.patch`.

## Future tests on its code

| Code | Future tests failing (of 228) | Regressions introduced |
|---|---|---|
| May snapshot, untouched | 9 | n/a |
| May snapshot + blind hardening | **5** | **0** |

## The 8 bugs that actually got reported after May

| Real fix (merged Aug–Oct 2026) | Blind agent |
|---|---|
| Regex flags missing from query hash (#640) | **Fixed** |
| `LRUCache` treats stored `None` as missing (#635) | **Fixed** |
| `insert_multiple` reuses IDs in mixed batches (#633) | **Fixed** |
| `touch()` fails for a bare filename (#619, no test) | **Fixed** |
| `Query.test()` crashes on unhashable args (#618) | Partly: handles lists, dicts and tuples, but a truly unhashable object still makes the query cacheable, which the real test checks |
| `CachingMiddleware` usable after close (#634) | Missed |
| `persist_empty` wipes existing table data (#642) | Missed |
| `Query.any/all` treat str/bytes as sequences (#641) | Missed (the agent fixed generators in any/all, not strings) |

Result: **4 of 8 anticipated outright, 1 partly.** The roadmap-style prediction (`1-predictions.md`) got 1 of 8.

## What this suggests

- Reading and probing the code finds future bug reports far better than predicting the roadmap does. "Future requirements" for a mature repo are mostly latent defects.
- The other 15 fixes aren't confirmed by the future (yet). Some may be real but unreported, and some may be over-engineering. Precision against confirmed future reports is 5 of 20. That's an upper bound on waste, not a measure of it.
- As a reward: future-test pass rate (9 → 5 failing) with zero regressions is a clean, automatic score. It can't credit fixes the future never tested, so it should be paired with a regression/no-churn penalty to stop models from rewriting everything.

Caveats: one run, one repo, one model. The agent's isolation was enforced by instructions, not a sandbox.
