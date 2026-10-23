# repomap: a traced map of a repo, for change impact and agent memory

A prototype built on werkzeug. It runs the test suite under Python's `sys.monitoring` and records three things:

- which package lines each test runs;
- who calls whom;
- a compact summary of the argument and return values every function actually saw.

From that map it answers two questions:

1. **What does this change affect?** It lists the pieces (modules and functions) and the tests a diff reaches. The prediction was scored against werkzeug's real commits after the snapshot.
2. **What has the code actually been exercised with?** It shows per-function value summaries and gaps (for example, "this argument was never empty"), for an agent to query instead of guessing from source.

The viewer is [Werkzeug Change Impact](https://claude.ai/artifact/9AEvdA1qQ2EcVkbdqfVmjq), a private artifact: pick a commit to see the changed functions, their callers grouped by module, and the predicted tests next to the ones actually affected.

## Everyday use: `repomap.py`

Record once, then look up a change before (or after) you make it, without running the tests:

```
repomap.py record --package src/werkzeug          # traces the suite once; werkzeug: 33 s, memory in .repomap/
repomap.py impact Range.range_for_length          # or path.py:LINE, or no argument for your uncommitted diff
repomap.py refresh                                # after a change: re-trace only tests that run the changed files
repomap.py status
```

```
$ repomap.py impact src/werkzeug/datastructures/range.py:110
Impact of named targets  (992 tests in memory, looked up in 0.12s)

Changed:
  werkzeug/datastructures/range.py:Range.range_for_length  (5 tests)

Callers (pieces that depend on it):
  direct  werkzeug.datastructures.range: Range.make_content_range, Range.to_content_range_header
  direct  werkzeug.wrappers.response: Response._process_range_request
    level 2  werkzeug.wrappers.response: Response.make_conditional

Tests that run it: 5 of 992
     5  tests/test_wrappers.py

Run them:
  python -m pytest -q tests/test_wrappers.py::test_range_request_basic …
```

The memory remembers the exact tree it traced (as a git commit under `refs/repomap/memory`, untracked files included), so `impact` with no arguments diffs your working tree against what was traced, not against HEAD. It also lists changed functions that no test runs: the memory can't say what depends on those.

**Tried on werkzeug's real history.** The first 8 upstream commits after the snapshot that touched library code were applied one at a time as uncommitted edits. Each was looked up with `impact` and then folded in with `refresh`:

- **Lookups** took 0.2 to 0.8 s each and named 16 to 335 of about 1,000 tests.
- **Refreshes** re-ran 55 to 419 tests and took 2 to 16 s each, compared with 33 s for a full record.
- **Accuracy after all 8 refreshes,** compared with a fresh full record of the same code:
  - same tests and identical call graph (1,707 edges);
  - identical line sets for 989 of 1,003 tests.

  The other 14 differ only in setup work that runs once per process (a shared routing map built by whichever test needs it first, file objects closed when garbage is collected). Which test gets credited for that depends on test order. A full re-record now and then resets it.

## Change impact on werkzeug's real history

There were 54 first-parent commits after the 2026-06-01 snapshot that touched `src/werkzeug`. For each commit C with parent P:

- **Map.** P's test suite is traced on P's code.
- **Ground truth.** P's tests are traced again on C's code. A test counts as affected if any of these holds:
  - it ran a changed line before or after the change;
  - it reached newly added code;
  - it took a different path through unchanged code (line numbers aligned through the diff);
  - its result changed.

  One test that varies between two runs of identical code was excluded.

| Predict from | Recall, any effect (3,286 test × commit pairs) | Recall, result changed (85) | Precision | Share of suite run |
|---|---|---|---|---|
| Changed lines | 99.9% | 83 of 85 | 73% | 8% |
| Changed functions | 100% | 85 of 85 | 24% | 24% |
| Changed files | 100% | 85 of 85 | 19% | 32% |
| Changed functions, map traced once at the snapshot and never refreshed | 89% | 80 of 85 | 51% | 10% |

What this says:

- **For existing tests, a fresh traced map predicts impact almost perfectly.** Selecting tests by changed functions caught every test whose result changed while running a quarter of the suite. Selecting by changed lines ran 8% of the suite and missed 2 of 85.
- **The map goes stale, but slowly.** A map traced once at the snapshot and never refreshed still caught 89% of affected tests (80 of 85 result changes) across five months of history. It fails on code that moved: when `HeaderSet` and `header_property` were moved or renamed, the old map no longer knows the names (`deprecate header_property`: 0 of 123).
- **Callers spread fast.** Following callers up 3 levels reaches a median of 7 modules per commit, and up to 36, because helpers like `cached_property` and `Request.url` sit under everything. In the viewer this is the "Callers" column. A useful "pieces" view probably needs clustering or a depth cut-off, not raw reach.

### Caveats

- **The ground truth comes from the same tracer as the prediction.** "Ran a changed line" is close to the line predictor by construction. The independent checks are the 85 tests whose result changed and the 567 whose path changed; the function map caught all of both.
- **Only existing tests are covered.** Tests that a commit adds can't be predicted from the parent's map. Effects that travel through data or configuration without changing any test's path or result are invisible here.
- **One repo, pure Python.** Tracing cost was about 1.4x a normal test run without the call graph and 2x with it.

## Value summaries as agent memory

`query.py` answers questions an agent would otherwise guess at:

```
$ query.py snapshot-map.json fn FloatConverter.to_url
werkzeug/routing/converters.py:FloatConverter.to_url  (line 232, 3 calls)
  value: float×3  [positive×3]  never: zero, negative
$ query.py snapshot-map.json fn Range.range_for_length
  length: int×9  [positive×9]  never: zero, negative
```

Both are places where werkzeug later fixed real bugs: float URLs for whole numbers and small values, and suffix ranges longer than the content. The full `gaps` view lists 375 functions with an argument never tried empty, zero or negative, so on its own it's a long list rather than a pointer. Whether it helps hardening agents find more future bugs is the next experiment.

## Files

- `repomap_trace.py`: the pytest plugin (`-p repomap_trace`, with `REPOMAP_ROOT`, `REPOMAP_OUT` and optional `REPOMAP_EDGES=1`).
- `repomap.py`: the everyday command (`record`, `impact`, `refresh`, `status`).
- `impact.py`: replays a repo's history and scores the predictors; `build_ui.py`: bundles results for the viewer; `query.py`: the agent-facing query tool.
- `werkzeug/`:
  - `impact.json`: per-commit truth and predictions;
  - `snapshot-map.json.gz`: the traced map with values and call graph;
  - `index.html` and `data.json`: the viewer.

## Next

- **A/B on hardening.** Give agents `query.py` (the gaps and value summaries) on the held-out repos and score them with future tests, as in `../pilot-future-reqs/ab-test/`.
- **Pieces by clustering.** Group functions that the same tests run together, instead of grouping by module, and check whether later upstream commits stay inside one cluster.
- **Patch impact for agents.** Show an agent's own patch in the viewer before it commits, so a reviewer sees what it reaches.
