# Repo lifetime simulation: training data exploration

Exploring whether models can be trained to write code that survives a repository's future, using real repos whose later history the model hasn't seen.

## Contents

- [`research/repo-evolution-training-data.md`](research/repo-evolution-training-data.md): survey of benchmarks (SWE-CI, SWE-Milestone, SWE-Chain, SWE-EVO), training datasets, and synthetic repo-evolution work as of October 2026, and where the gaps are.
- [`pilot/`](pilot/README.md): pilot of "simulate future requirements" on tinydb and click.
  - `future_tests.sh` runs a repo's later test suite against its code as of a cutoff date.
  - `tinydb/1-predictions.md`: blind roadmap predictions (1 of 8 real bug fixes anticipated).
  - `tinydb/2-what-shipped-and-score.md`: what actually shipped after May 2026.
  - `tinydb/3-blind-hardening.md` and `blind-hardening.patch`: a fresh agent hardened the May code. Failing future tests went from 9 to 5 with 0 regressions, and it anticipated 4 of the 8 later bug reports outright plus 1 partly.

## Headline findings

1. Public work on repo evolution is mostly benchmarks. Training data at "repo lifetime" scale is early and largely unpublished.
2. Running a repo's future tests against its past code gives an automatic reward for "future-proof" code.
3. For a mature repo, the future is mostly latent bugs. Probing the code anticipates them far better than predicting the roadmap.

## Next steps

- Repeat the blind run on 5 to 10 repos with post-cutoff history, several runs each.
- Filter feature-addition tests (as in click) down to APIs that existed at the snapshot.
- Package it as an RL environment: reward = future tests fixed − regressions − churn penalty.
