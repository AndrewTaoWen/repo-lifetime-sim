# Scale-up: blind hardening on 8 repos, scored by their future tests

**Question.** If an agent is given a repo as it stood at the model's knowledge cutoff (2026-06-01) and asked to "make it robust for the future", how many of the bugs that real users later reported and real maintainers later fixed does it anticipate?

**Answer so far.** About a quarter. Pooled over 24 runs, blind hardening made 267 of 1,032 (26%) target future tests pass, with 3 regressions in total. tomlkit is a large share of that pool; the average of the per-repo rates is 22%, and without tomlkit the pooled rate is 19%. Results are consistent across runs for libraries with clear latent bugs (more-itertools, tinydb, sqlparse) and weak where the future is mostly new features (pluggy) or new semantics (attrs).

## Method

1. **Screen** (`../screen.py`). For each candidate repo: take the last commit before 2026-06-01 (the snapshot) and the current HEAD. Run HEAD's test suite against HEAD's code, then against the snapshot's package code. Tests that pass on HEAD but fail on the snapshot are the *target*: future requirements the snapshot doesn't meet.
2. **Blind hardening** (`../blind.py prep`). Three independent workspaces per repo, each a bare copy of the snapshot (its own git repo, no upstream history, no network instructions to fetch anything). A fresh agent is told only: find and fix latent bugs and edge cases a maintainer would want fixed, keep the existing tests passing, commit your work. It never sees the future tests.
3. **Score** (`../blind.py score`). Swap each run's package code into the HEAD tree and run HEAD's tests. *Fixed* = target tests that now pass. *Regression* = a future test that passes on the untouched snapshot but fails after hardening.

19 repos were screened and 8 were run. Of the rest, 8 had no usable future tests or broke the harness (boltons, dateutil, humanize, markupsafe, packaging, platformdirs, tenacity, toolz), tomli had only 1, and python-dotenv (33) and cattrs (44) were found in a later screen and are good candidates for the next round.

## Results

| Repo | Future tests failing on snapshot | Fixed per run (r1, r2, r3) | Mean | Fixed by any run | Fixed by every run | Regressions |
|---|---|---|---|---|---|---|
| attrs | 10 | 0, 0, 0 | 0% | 0 | 0 | 0 |
| cachetools | 41 | 8, 7, 12 | 22% | 12 | 7 | 1 |
| marshmallow | 8 | 1, 1, 1 | 12% | 1 | 1 | 0 |
| more-itertools | 40 | 11, 11, 11 | 28% | 11 | 11 | 0 |
| pluggy | 65 | 7, 9, 6 | 11% | 11 | 2 | 0 |
| sqlparse | 10 | 3, 3, 2 | 27% | 3 | 2 | 0 |
| tinydb | 9 | 4, 3, 4 | 41% | 4 | 3 | 0 |
| tomlkit | 161 | 56, 52, 55 | 34% | 61 | 48 | 2 |

Pooled: 267/1032 = 25.9% over 24 runs

"Fixed by any run" is the union over the three runs; "fixed by every run" is the intersection.

## What was and wasn't anticipated

Grouping each repo's target tests by test class shows the split between latent bugs (anticipated often) and new behaviour (almost never).

- **tinydb** (best, 41%). Caught `insert_multiple` with mixed documents, regex flags in `search`/`matches`, and persisting empty tables. Missed caching-middleware `close`, `any`/`all` on strings, unhashable query parameters and LRU cache with `None` capacity.
- **more-itertools** (28%, identical 11 tests in all three runs). Caught edge cases in `bucket`, `numeric_range`, `combination_with_replacement_index`, `interleave_evenly` and `value_chain`. Missed `seekable`, `subfactorial` and running-window size, which are new behaviour.
- **sqlparse** (27%). Caught output-format and lowercase `CREATE | Repo | Future tests failing on snapshot | Fixed per run (r1, r2, r3) | Mean | Fixed by any run | Fixed by every run | Regressions |
|---|---|---|---|---|---|---|
| attrs | 10 | 0, 0, 0 | 0% | 0 | 0 | 0 |
| cachetools | 41 | 8, 7, 12 | 22% | 12 | 7 | 1 |
| marshmallow | 8 | 1, 1, 1 | 12% | 1 | 1 | 0 |
| more-itertools | 40 | 11, 11, 11 | 28% | 11 | 11 | 0 |
| pluggy | 65 | 7, 9, 6 | 11% | 11 | 2 | 0 |
| sqlparse | 10 | 3, 3, 2 | 27% | 3 | 2 | 0 |
| tinydb | 9 | 4, 3, 4 | 41% | 4 | 3 | 0 |
| tomlkit | 161 | 56, 52, 55 | 34% | 61 | 48 | 2 |

Pooled: 267/1032 = 25.9% over 24 runs AS` bugs. Missed DoS-prevention limits, three specific issue regressions and dotted-name parsing.
- **cachetools** (22%). Caught 4 of 5 `cachedmethod` unbound-method tests and some TTL/TLRU edge cases. Missed the `None`-wrapper behaviour change. Run 3 introduced one regression (`UnboundMethodTest::test_autospec_call`).
- **marshmallow** (12%). Every run caught `TimeDelta` with NaN. None caught the `Pluck` or URL-validator changes, even though all three claimed to fix relative URLs.
- **pluggy** (11%). The target is dominated by new tracer and hookspec-default-argument features (e.g. `TestHookspecDefaultArgumentValue`, 12 tests) that no agent could have guessed. It did catch register/validation rollback, falsy plugins, `specname` and dict-result tracing. Only 2 tests were fixed by every run, so this is the noisiest repo.
- **attrs** (0%). Misses are `TestSetAttr` (8 tests), `is_class_var` and `TestReplace`, all intentional semantic changes rather than bugs.
- **tomlkit** (34%, the largest target at 161 tests). Every run caught rejecting non-lowercase `inf`/`nan` (28 parametrized cases), non-hex and surrogate unicode escapes, tabs in bare keys, malformed array-of-tables headers and slice assignment mutating arrays. None caught round-tripping emptied nested arrays of tables, preserving underscores in integers, the nesting depth limit or rejecting tables redefined after their parent. Run 2 broke two table-membership tests, the other 2 of the 3 regressions.

## Precision

Agents claimed 4 to 22 fixes per run (about 14 on average). Most of those claims can't be checked: they don't correspond to any future test, so they're either real bugs nobody has reported yet, or unnecessary changes. In tinydb, for example, runs claimed about 20 fixes each and 3 to 4 matched the future. This is the same picture as the pilot: recall against real future bugs is meaningful, precision is unknown.

## Caveats

- **Target sets include features, not just bugs.** No agent is expected to guess pluggy's tracer API or attrs' `replace` semantics. A fairer denominator would label each target test as "latent bug" or "new feature" first; this hasn't been done.
- **Isolation was enforced by instructions, not a sandbox.** Agents had no repo history or network instruction, but nothing physically stopped them. Round-1 agents wrote probe files outside their workspace (into a shared scratch folder); later prompts told them to keep scratch files inside the workspace. No agent was seen reading another run's workspace or fetching upstream code, but this wasn't verified mechanically.
- **Interrupted runs.** A usage limit paused several agents twice; they were resumed with their context intact, so some runs had two sessions.
- **Parametrized tests count once per case.** One fix can move many tests (tomlkit's special-float check is 28 of its 161), so per-test rates overweight a few fixes.
- **Small n.** 8 repos, 3 runs each, all small pure-Python libraries.

## Files

- `scores.json`: per-run scores, fixed and regressed test IDs, diff size.
- `patches/<repo>-r<k>.patch`: every agent's changes against the snapshot.
- `screen/<repo>.json`: snapshot/HEAD commits and dates, target test IDs, for all 19 screened repos.
- `agents.txt`: run log.
- `../screen.py`, `../blind.py`: the harness.

## Next

1. Label each target test as bug vs feature and report recall on bugs only.
2. Run in a real sandbox (no network, workspace-only filesystem) to close the isolation gap.
3. Use the confirmed fixes as reward: train or prompt for hardening and see whether recall on held-out repos goes up without more regressions.
