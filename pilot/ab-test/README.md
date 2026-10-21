# Prompt A/B test: does a miss-analysis prompt catch more future bugs?

**Question.** `../analysis/` found that hardening agents miss whole kinds of bugs, such as degenerate inputs, falsy-vs-missing values, round-tripping, spec conformance and performance. If the prompt tells the agent to search those kinds deliberately, does it catch more of the bugs that real users later reported, without more regressions?

**Answer.** Probably yes, but by a modest amount, and the evidence is thin. Over 4 held-out repos with 2 runs per arm:

- The improved prompt caught **21 of 60** run × bug pairs against the baseline's **15 of 60**, counting distinct upstream bugs (35% vs 25%).
- Taking the union of each arm's two runs, it caught **13 of 30** bugs against **9 of 30**.
- It was ahead or tied on every repo, and neither arm caused a single regression.
- The improved runs also wrote about a third more regression tests that fail on the snapshot code (265 vs 197).
- Much of the gain comes from python-dotenv, which is the repo where the prompt is least clean (see caveats). On werkzeug and pydantic-settings, the two cleanest repos, the gain is 9 vs 6 run × bug pairs, which is within noise at this n.

## Setup

- **Repos.** python-dotenv, cattrs, werkzeug and pydantic-settings, all newly screened (`screen/`), none used in earlier rounds. Snapshot is the last commit before 2026-06-01, as before.
- **Arms.** r1 and r2 got the round-1 prompt (`prompt-baseline.txt`). r3 and r4 got the same prompt plus a "How to search" block (`prompt-improved.txt`) written from the miss analysis: go breadth-first, then check degenerate and falsy inputs, round-trips, spec conformance in both directions, the library's own exception types, hostile values, state after copy/pickle/close, and performance at 10x and 100x.
- **Runs.** 16 fresh agents, one per workspace under `/srv/blind4`, with the same isolation rules as round 2. A usage limit stopped 12 of them partway through; they were resumed with their context intact (`agents.txt`).
- **Scoring.** Same as before (`../blind.py score`). Each run's code goes into the future tree and HEAD's tests run against it. Tests are labelled bug, feature or unclear by the commit that added them (`labels-heldout.json` plus `../scale-up/label-overrides.json`). Recall is counted two ways:
  - **bug tests:** parametrized cases count separately;
  - **distinct bugs:** tests are grouped by the upstream commit that added them. This is the main measure, because one cattrs fix alone moves 21 parametrized tests.
- **Verified regression tests** (`verify.sh`). The agent's own test files are run against the snapshot's package code. Tests that fail there, and don't already fail on the untouched snapshot, count as verified. This is the "credit fixes the future hasn't reported yet" half of the reward suggested in `../analysis/`.

## Results

Distinct future bugs caught, per run and as the union over each arm's two runs:

| Repo | Bugs | Baseline r1, r2 | Union | Improved r3, r4 | Union |
|---|---|---|---|---|---|
| python-dotenv | 7 | 1, 1 | 1 | 3, 2 | 3 |
| cattrs | 7 | 3, 4 | 4 | 4, 3 | 4 |
| werkzeug | 10 | 3, 2 | 3 | 2, 5 | 5 |
| pydantic-settings | 6 | 0, 1 | 1 | 1, 1 | 1 |
| **Total** | **30** | **15 of 60 (25%)** | **9 (30%)** | **21 of 60 (35%)** | **13 (43%)** |

Other measures:

| | Baseline | Improved |
|---|---|---|
| Bug tests fixed, parametrized cases counted (of 111 per run) | 6, 3, 5, 26, 6, 4, 0, 1 = 51 | 16, 7, 6, 5, 7, 10, 1, 1 = 53 |
| Feature tests fixed | 0 | 0 |
| Regressions (future tests broken) | 0 | 0 |
| Fixes claimed (agent reports) | 128 | about 129 |
| Agent regression tests that fail on the snapshot code | 197 | 265 |

What the improved prompt caught that the baseline didn't:

- **python-dotenv:** `dotenv get` exiting non-zero for an empty value, and an empty unquoted value followed by an inline comment (`a= #c`). Both are empty-value cases, which the prompt names.
- **werkzeug:**
  - preserving an empty username, an empty password and port 0 in URLs;
  - numeric ordering of more than 10 converters in one rule segment;
  - treating `bytes=-0` as an invalid range.

  These are degenerate-input and spec-conformance cases.
- **cattrs:** sorted keys in `ForbiddenExtraKeysError`.

The baseline caught one cattrs bug that the improved runs didn't: renamed literal fields in union disambiguation. That one fix is the 21 parametrized tests that make cattrs r2 look like the best run when counting tests.

## What this says

- **The direction is consistent, but the size isn't established.** The improved prompt is ahead or tied on all 4 repos by distinct bugs, and ahead on 3. With 2 runs per arm, and run-to-run spread as large as the gap (werkzeug improved: 2 vs 5), this is suggestive, not conclusive.
- **It found its extra bugs in the kinds it pointed at.** The extra bugs are empty values, port 0, an empty username, `-0` and ordering past 10 items. The state and caching bugs both arms were already good at stayed the same.
- **There was no cost in safety.** Neither arm broke a future test. The fixes are the same size and number, and the improved runs left more verified regression tests behind.
- **The verified-test count is a fair but imperfect way to pick a run.** Within each arm and repo, picking the run with more verified regression tests chooses the run that caught more future bugs in 4 of the 5 pairs where the two runs differ. The exception is improved python-dotenv, where it picks the 2-bug run over the 3-bug one. It also measures something the future tests can't, namely bugs nobody has reported yet.

## Caveats

- **The prompt isn't fully blind to two of the repos.** It was written after the python-dotenv and cattrs label lists had been on screen while setting up the screens. Two lines that echoed python-dotenv labels were removed before any run ("~ expansion / error messages naming the file" and "cleanup must not mask errors"). The remaining "empty / falsy" line comes from round 1's more-itertools and tinydb misses, but python-dotenv's two extra catches are exactly empty-value bugs. Treat the python-dotenv gain as an upper bound. werkzeug and pydantic-settings labels came after the prompt was fixed.
- **Future data stayed on disk this round.** The screens were still running when the agents launched. Isolation rests on the transcript audit (`audit.json`, `../audit.py`), which found:
  - no web calls;
  - no reads of future clones, labels or other workspaces.

  The 4 "network" flags are github.com links inside changelog or code text being edited. The 3 "sensitive" flags are agents reading their own background test-run output files.
- **Labels.** werkzeug's catch-all rule labelled every test with no identified adding commit as a feature. Six of those were placed by hand with `git log -S`; four turned out to be bug fixes (host port validation, stricter int parsing, invalid etags, `bytes=-0`), one a feature and one unclear. This was done after scoring, and it moves one improved-run bug (`bytes=-0`). The same lookup grouped python-dotenv's parametrized parser cases under their two fix commits. The mapping is in `ab.py` (`FOUND`).
- **The pre-existing failures differ by repo.** On pydantic-settings, 7 CLI tests fail on the untouched snapshot because the venv has a newer pydantic. Baseline r1 fixed that compatibility issue too. Those tests aren't counted as verified for any run.
- **Small n.** 4 repos, 2 runs per arm, all pure-Python libraries. Tests and bug kinds are uneven across repos.

## Files

- `README.md`: this write-up.
- `prompt-baseline.txt`, `prompt-improved.txt`: the exact prompts, as given to the python-dotenv runs (other repos differ only in paths and the test command).
- `scores.json`: per-run future-test scores; `results.json`: bug-only recall, distinct bugs and verified tests per run.
- `labels-heldout.json`: auto labels for the 4 repos' target tests; hand overrides are in `../scale-up/label-overrides.json`.
- `screen/`: screen results (snapshot, HEAD, target tests) for the 4 repos.
- `patches/<repo>-r<k>.patch`: every agent's changes against the snapshot.
- `audit.json`: transcript audit; `agents.txt`: run log.
- `ab.py`: recomputes `results.json` (`python3 ab.py . results.json scores.json`).
- `verify.sh`, `verify-base.sh`, `junitfails.py`: the snapshot-failing check for agent tests.

## Next

- More runs per arm on werkzeug and pydantic-settings, the clean repos, to see whether the gap holds.
- Run the improved prompt on round 1's repos, where per-kind miss data already exists, to see which weak kinds move.
- Have a reviewer check the verified regression tests (as in `../analysis/precision`) before counting them in a reward.
