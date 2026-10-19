# tinydb: what actually shipped after the snapshot, and how the predictions scored

Future window: `a7174d1` (2026-05-28) to `edff96a` (2026-10-15). v4.9.0 released 2026-08-06, plus 15 commits since.

## Actual changes, matched against predictions

| # | What shipped | Kind | Matched by |
|---|---|---|---|
| A1 | v4.9.0 released with the #591 doc_ids fix | release | **P1 hit** |
| A2 | `Table.update` / operations type hints switched to MutableMapping (#621) | typing | **P2 hit** |
| A3 | Changelog: drop Python 3.8/3.9 (code already required 3.10) | infra | P4 wrong direction (miss) |
| A4 | `Query.test()` crashes on unhashable extra args (#618) | latent bug | miss |
| A5 | `storages.touch()` FileNotFoundError for a bare filename (#619) | latent bug | P6 partial (storage robustness, different bug) |
| A6 | `LRUCache` treats stored `None` as missing (#635) | latent bug | miss |
| A7 | `insert_multiple` reuses IDs in mixed Document/dict batches (#633) | latent bug | P3 partial (doc_id edge cases) |
| A8 | `CachingMiddleware` allows reads/writes after close (#634) | latent bug | **P7 hit** |
| A9 | Regex flags missing from `matches`/`search` query hash, so cache returns wrong results (#640) | latent bug | miss |
| A10 | `persist_empty` wipes existing table data (#642) | latent bug | miss |
| A11 | `Query.any/all` treat str/bytes as sequences (#641) | latent bug | miss |
| A12 | Docs: architecture overview, AI-assistance guidelines, cache-sharing note, moving docs between DBs, docs/type-hint alignment | docs | **P9 hit** (topics differ) |
| A13 | Extensions list updated | docs | **P9 hit** |
| A14 | Dependency bumps | chore | **P11 hit** |

Predictions that didn't happen: P4 (drop 3.10 / add 3.15), P5 (new Query helpers), P8 (update_multiple/upsert follow-ups), P10 (performance).

## Score

- Overall: 7 of 11 predictions hit at least partially; 8 of 14 actual changes were anticipated at least partially.
- **But the hits are the generic ones** (release, typing, docs, deps). Of the 8 substantive code changes (A4 to A11, all latent bugs), only 1 was predicted outright and 2 partially.
- What the future actually demanded was **edge-case correctness in code that already existed**: cache keys that ignore inputs, `None`/falsy confusion, str-as-sequence, ID reuse, state after close. None of it was a new feature, which fits a project in maintenance mode.

## Executable version of the future

Running today's test suite against the May snapshot code (`future_tests.sh`): **9 of 228 tests fail**, covering 7 of the 8 latent bugs above (`touch()` has no failing test). Those 9 tests are an objective "did this code survive its future" signal for this snapshot.
