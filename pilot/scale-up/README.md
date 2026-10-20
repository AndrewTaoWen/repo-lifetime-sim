# Scale-up: blind hardening on 8 repos, scored by their future tests

**Question.** If an agent is given a repo as it stood at the model's knowledge cutoff (2026-06-01) and asked to "make it robust for the future", how many of the bugs that real users later reported and real maintainers later fixed does it anticipate?

**Answer so far.** About a quarter to a third of real future bugs, and none of the new features. Pooled over 24 runs, blind hardening made 267 of 1,032 (26%) target future tests pass, with 3 regressions in total. Counting only tests that check bug fixes, recall is 32% pooled (264 of 834), and 25% averaged per repo. Not one of the 49 tests for new features or deliberate behaviour changes was ever fixed. A second round of 8 runs with the future data moved off disk and every agent's tool calls audited scored about the same on 7 of 8 repos (per-repo average 32% on bugs); tomlkit was the exception (12% vs 36%), most likely run-to-run variance in what the single agent chose to look at.

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

## Bug vs feature

Each target test was labelled by the upstream commit that added it (`../label.py` finds the commit; the labels themselves are by hand in `label-overrides.json`, with the per-test result in `labels.json`). *Bug* means a defect in behaviour that already existed at the snapshot; *feature* means a new API, option or deliberate behaviour change; *unclear* is a test-only refactor whose underlying change isn't identifiable.

| Repo | Bug | Feature | Unclear | Bug tests fixed per run (r1, r2, r3) | Bug recall (mean) |
|---|---|---|---|---|---|
| attrs | 2 | 8 | 0 | 0, 0, 0 | 0% |
| cachetools | 31 | 0 | 10 | 7, 7, 10 | 26% |
| marshmallow | 7 | 1 | 0 | 1, 1, 1 | 14% |
| more-itertools | 32 | 8 | 0 | 11, 11, 11 | 34% |
| pluggy | 37 | 28 | 0 | 7, 9, 6 | 20% |
| sqlparse | 8 | 2 | 0 | 3, 3, 2 | 33% |
| tinydb | 9 | 0 | 0 | 4, 3, 4 | 41% |
| tomlkit | 152 | 2 | 7 | 56, 52, 55 | 36% |
| **All** | **278** | **49** | **17** | | **32% pooled, 25% per-repo mean** |

Feature tests fixed: 0 in all 24 runs. The labels were made from commit subjects before looking at which tests were fixed, so this isn't circular. attrs drops out as a signal: 8 of its 10 targets are the new generator support in `on_setattr`.

## Sandboxed rerun (round 2)

Round 1's isolation was only instructions, and the repo clones with full future history sat in a sibling folder. Round 2 ran 1 fresh agent per repo with the same prompt and these changes:

- New workspaces under `/srv/blind3`; the clones, future trees, screen results, labels and round-1 workspaces were moved out of the scratch area during the runs.
- Every agent's tool calls were audited afterwards with `../audit.py`: no web tools, no network commands (pip, curl, git fetch...), no paths outside the workspace except the Python install. All 8 came back clean. The same audit on the 15 round-1 transcripts that still exist (the other 9 were lost when an earlier container was recycled) found no network use and no reads of future data, only the probe files written to the scratch root.
- The agent could still in principle have read the shared project folder or session logs; the audit is what shows it didn't.

| Repo | Bug tests fixed, round 1 mean | Round 2 (sandboxed) | Round 2 all targets | Regressions |
|---|---|---|---|---|
| attrs | 0.0 of 2 | 1 (50%) | 1/10 | 0 |
| cachetools | 8.0 of 31 | 10 (32%) | 12/41 | 1 (the same `test_autospec_call` as round 1) |
| marshmallow | 1.0 of 7 | 1 (14%) | 1/8 | 0 |
| more-itertools | 11.0 of 32 | 13 (41%) | 13/40 | 0 |
| pluggy | 7.3 of 37 | 6 (16%) | 6/65 | 0 |
| sqlparse | 2.7 of 8 | 3 (38%) | 3/10 | 0 |
| tinydb | 3.7 of 9 | 5 (56%) | 5/9 | 0 |
| tomlkit | 54.3 of 152 | 19 (12%) | 19/161 | 0 |

Round 2's per-repo average bug recall is 32% against round 1's 25%; pooled it is 21% (58 of 278), lower only because of tomlkit. All three round-1 tomlkit agents found that the parser accepted `Inf`/`NaN`/`Infinity` spellings (31 parametrized tests); the round-2 agent spent its effort on document-editing and performance bugs instead, fixing 22 things that mostly have no future test yet. With one run per repo this can't be separated from variance, but there's no sign that round 1's results depended on leaked data.

## What was and wasn't anticipated

Grouping each repo's target tests by test class shows the split between latent bugs (anticipated often) and new behaviour (almost never).

- **tinydb** (best, 41%). Caught `insert_multiple` with mixed documents, regex flags in `search`/`matches`, and persisting empty tables. Missed caching-middleware `close`, `any`/`all` on strings, unhashable query parameters and LRU cache with `None` capacity.
- **more-itertools** (28%, identical 11 tests in all three runs). Caught edge cases in `bucket`, `numeric_range`, `combination_with_replacement_index`, `interleave_evenly` and `value_chain`. Missed `seekable`, `subfactorial` and running-window size, which are new behaviour.
- **sqlparse** (27%). Caught output-format and lowercase `CREATE TABLE AS` bugs. Missed DoS-prevention limits, three specific issue regressions and dotted-name parsing.
- **cachetools** (22%). Caught 4 of 5 `cachedmethod` unbound-method tests and some TTL/TLRU edge cases. Missed the `None`-wrapper behaviour change. Run 3 introduced one regression (`UnboundMethodTest::test_autospec_call`).
- **marshmallow** (12%). Every run caught `TimeDelta` with NaN. None caught the `Pluck` or URL-validator changes, even though all three claimed to fix relative URLs.
- **pluggy** (11%). The target is dominated by new tracer and hookspec-default-argument features (e.g. `TestHookspecDefaultArgumentValue`, 12 tests) that no agent could have guessed. It did catch register/validation rollback, falsy plugins, `specname` and dict-result tracing. Only 2 tests were fixed by every run, so this is the noisiest repo.
- **attrs** (0%). Misses are `TestSetAttr` (8 tests), `is_class_var` and `TestReplace`, all intentional semantic changes rather than bugs.
- **tomlkit** (34%, the largest target at 161 tests). Every run caught rejecting non-lowercase `inf`/`nan` (28 parametrized cases), non-hex and surrogate unicode escapes, tabs in bare keys, malformed array-of-tables headers and slice assignment mutating arrays. None caught round-tripping emptied nested arrays of tables, preserving underscores in integers, the nesting depth limit or rejecting tables redefined after their parent. Run 2 broke two table-membership tests, the other 2 of the 3 regressions.

## Precision

Agents claimed 4 to 22 fixes per run (about 14 on average). Most of those claims can't be checked: they don't correspond to any future test, so they're either real bugs nobody has reported yet, or unnecessary changes. In tinydb, for example, runs claimed about 20 fixes each and 3 to 4 matched the future. This is the same picture as the pilot: recall against real future bugs is meaningful, precision is unknown.

## Caveats

- **Bug/feature labels are one person's judgement** from commit subjects. The 17 unclear tests are excluded from both counts.
- **Isolation is audited, not enforced.** Neither round ran in an OS-level sandbox (not available in this environment). Round 2 moved the future data away and audited every tool call; round 1 can only be audited for 15 of 24 runs.
- **Interrupted runs.** A usage limit paused several agents twice; they were resumed with their context intact, so some runs had two sessions.
- **Parametrized tests count once per case.** One fix can move many tests (tomlkit's special-float check is 28 of its 161), so per-test rates overweight a few fixes.
- **Small n.** 8 repos, 3 runs each, all small pure-Python libraries.

## Files

- `scores.json`: per-run scores, fixed and regressed test IDs, diff size.
- `patches/<repo>-r<k>.patch`: every agent's changes against the snapshot.
- `screen/<repo>.json`: snapshot/HEAD commits and dates, target test IDs, for all 19 screened repos.
- `agents.txt`: run log.
- `labels.json`, `label-overrides.json`: bug/feature label for every target test.
- `sandboxed/`: round-2 scores, patches and audit report.
- `../label.py`, `../audit.py`: labelling and transcript-audit scripts.
- `../screen.py`, `../blind.py`: the harness.

## Next

1. More sandboxed runs per repo (and python-dotenv, cattrs) to separate tomlkit-style variance from real differences.
2. Use the confirmed fixes as reward: train or prompt for hardening and see whether recall on held-out repos goes up without more regressions.
