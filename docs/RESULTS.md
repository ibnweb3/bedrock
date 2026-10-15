# Backtest results (first run)

Produced by `scripts/compute_features.py` (Cypher in FalkorDB) and `scripts/evaluate.py`, following the
pre-registered design in `docs/BACKTEST_DESIGN.md`. Raw output is in `data/staging/results_<T0>.json`
(git-ignored; reproduce with the commands in the README). All numbers below are copied from those runs.

**Headline: the pre-registered success criterion was NOT met.** No graph method showed an improvement over
the best baseline whose paired 95% interval excluded zero at the primary or secondary cutoff.

## Primary: stratum H, T0 = 2020-12-31 (134,798 candidates, 140 positives, base rate 0.104%)

| Method | AP | Recall@1% (lift) | Recall@5% |
|---|---|---|---|
| random (control) | 0.0012 | 0.016 (1.6x) | 0.054 |
| b_venue_count | 0.0056 | 0.000 (0x) | 0.554 |
| b_venue_rate (best baseline) | 0.0066 | 0.000 (0x) | 0.550 |
| b_cites_asof | 0.0027 | 0.029 (2.9x) | 0.217 |
| b_author_prior (author distance 0, one-hop) | 0.0032 | 0.077 (7.7x) | 0.194 |
| g_contam1 (cites a retracted paper) | 0.0066 | 0.100 (10.0x) | 0.143 |
| g_contam2 (2 citation hops) | 0.0021 | 0.073 (7.3x) | 0.117 |
| g_coauth1 (co-author distance 1) | 0.0023 | 0.021 (2.1x) | 0.099 |
| g_coupled_w (coupled to retracted papers) | 0.0015 | 0.014 (1.4x) | 0.050 |
| g_comm_rate (community retraction share) | 0.0021 | 0.014 (1.4x) | 0.064 |
| G_COMP (graph composite) | 0.0041 | 0.071 (7.1x) | 0.286 |
| COMBINED (venue count + graph) | 0.0074 | 0.157 (15.7x) | 0.379 |

Paired AP differences, venue-clustered bootstrap (B = 300), 95% interval:
COMBINED - BASE_BEST [-0.0053, +0.0053] (includes 0); G_COMP - BASE_BEST [-0.0093, +0.0026] (includes 0).

## Other cutoffs (stratum H)

| T0 | Positives | Top venue's share | BASE_BEST AP | G_COMP AP | COMBINED AP | COMBINED - BASE_BEST (95%) |
|---|---|---|---|---|---|---|
| 2021-12-31 (secondary) | 140 | 38% | 0.0053 (b_venue_count) | 0.0024 | 0.0040 | [-0.0082, +0.0058] includes 0 |
| 2022-12-31 (regime check) | 481 | 88% | 0.0049 (b_venue_rate) | 0.0027 | 0.0028 | [-0.0067, +0.0015] includes 0; G_COMP - BASE_BEST [-0.0066, -0.0003] graph worse |

At T0 = 2022 nothing separates from the random control (AP 0.0038 at a 0.35% base rate); one venue holds 88% of positives.

## Robustness: excluding the venue with the most positives (T0 = 2020, 64 positives left)

Best baseline becomes b_author_prior (AP 0.0022). g_contam1 AP 0.0115 (lift 12.2x at 1%), COMBINED 0.0038, G_COMP 0.0027.
COMBINED - b_venue_count [+0.0004, +0.0065] excludes 0, but COMBINED - BASE_BEST [-0.0005, +0.0053] includes 0, and the
pre-registered comparison is against BASE_BEST. The g_contam1 interval is very wide ([0.0007, 0.0524]).

## What can and cannot be said

- Venue history is as good a predictor as any graph signal here (AP), and cheaper.
- Every graph signal beats random, and direct contamination (`g_contam1`) concentrates positives at the very top
  of the list better than venue baselines do (recall@1% of 10% vs 0%): a paper that cites already-retracted work
  is roughly 5-12x more likely than average to be retracted later. This is a one-hop join, not a multi-hop result.
- **The multi-hop signals did not beat their one-hop counterparts**: g_contam2 < g_contam1 and g_coauth1 <
  b_author_prior at every cutoff. The ablation the design required therefore says: no evidence multi-hop adds value.
- Power is very low. Positives come from 20-27 venues and the largest venue holds 38-88% of them, so intervals are wide.
  These results cannot distinguish "no effect" from "a modest effect"; they do not prove the graph is useless.
- Controls behave: `oracle` AP = 1.0, `random` AP about the base rate.
- Known leakage (author retention uses >= 2 papers over 2017-2022; coupling filter uses all-time in-degree) is
  listed in BACKTEST_DESIGN.md; it can only flatter the graph signals, and they still did not win.
