# tinydb: predicted next requirements (written blind)

Snapshot: `a7174d1` (2026-05-28), last commit before 2026-06-01. Predictor saw only the snapshot tree, its changelog and its own past commits. Future history was not read until this file was written. The predictor's knowledge cutoff is June 2026, so it has no memory of what came next.

Context used: README says maintenance mode (bugfixes and community features only). Unreleased changelog has one fix (#591: skip missing doc_ids). Recent commits are typing cleanups (collections.abc, MutableMapping), dependency bumps, docs. Supports Python 3.10 to 3.14.

| # | Predicted requirement | Kind | P(ships by next release) |
|---|---|---|---|
| P1 | Release 4.9.0 (or 4.8.3) that ships the #591 doc_ids fix | release | 0.85 |
| P2 | More typing tightening: Mapping/MutableMapping/Iterable in Table, Query and Storage signatures; mypy/pyright strictness | refactor | 0.7 |
| P3 | Make `Table.contains(doc_id=...)` / `get(doc_ids=...)` / `remove` / `update` consistent on edge cases (empty iterables, duplicates, missing IDs) | fix | 0.5 |
| P4 | Drop Python 3.10 or add 3.15 classifier/CI | infra | 0.35 |
| P5 | New query helper(s) on `Query` (e.g. `noneof`/`not_one_of`, case-insensitive match, `startswith`) contributed by community | feature | 0.25 |
| P6 | Storage robustness: atomic JSON writes (temp file + rename) or better handling of corrupted/empty JSON files | fix | 0.3 |
| P7 | `CachingMiddleware` fixes (flush on close / context manager, write-count edge cases) | fix | 0.25 |
| P8 | `update_multiple` / `upsert` behaviour or doc fixes aligned with the #591 change (return values, doc_id handling) | fix | 0.4 |
| P9 | Docs: security / callable-safety and extension list updates | docs | 0.6 |
| P10 | Performance: faster `insert_multiple`/`search` or doc ID conversion | perf | 0.15 |
| P11 | Dependency / tooling updates (uv, ruff, CI matrix) | chore | 0.8 |
