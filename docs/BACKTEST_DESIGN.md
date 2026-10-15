# Backtest design

Status: **design, written before any result exists.** Numbers will appear in the README only
when produced by scripts in this repo. Participant to review and confirm (see DECISIONS.md).

## Question

Using only what was known at a cutoff date T0, can graph signals rank papers by how likely they
are to be retracted in the following 24 months, better than non-graph baselines?

## Unit, label, cutoffs

- **Unit:** a research article (`type:article`) published in the 4 years up to T0, in a venue
  from the pool below, **not retracted on or before T0**.
- **Label (positive):** Retraction Watch lists the paper (by original DOI) with
  `RetractionNature = Retraction` and a retraction date in (T0, T0 + 24 months].
- **Cutoffs:** T0 = 2020-12-31 and T0 = 2022-12-31, both reported. The second window contains
  the 2023 mass-retraction wave (13,269 retractions dated 2023 in the data), a different regime
  from the first; results must not be pooled.

## Venue pool (candidate selection)

Selection script: `scripts/select_venues.py` -> `data/staging/venues.json` (seeds recorded).

- Stratified by retraction history **known at the selection cutoff (2020-12-31)**:
  H (>= 3 retractions), L (1-2), Z (none; random journals from a seeded OpenAlex sample).
- Size filter: 300-3,000 works over 2017-2022, journals only (bounds cost and graph size).
- **Selection uses pre-cutoff counts only.** Post-cutoff counts are written to the file under
  `diagnostics` and labelled as such; they are a feasibility check (do we get enough positives?)
  and never choose venues. If the pool yields too few positives, the *design* is revised in the
  open and the change is logged in DECISIONS.md.
- The pool is a stratified convenience sample, **not** representative of all literature. Absolute
  precision/AUPRC are therefore pool-specific; only comparisons between methods on the same pool
  are meaningful.

## Information allowed at T0 (leakage control)

Allowed: papers/references/authorships published <= T0; retractions dated <= T0.
Not allowed: anything dated after T0, including later retractions, later citations, and
`cited_by` counts. Known leak that cannot be removed: OpenAlex author-ID disambiguation is
computed on current data. Reported as a limitation.

## Signals (all computed inside FalkorDB)

1. Contamination: share/count of a paper's references (1-3 hops) retracted by T0.
2. Co-author proximity: hops to authors (hashed IDs) of papers retracted by T0.
3. Community: retraction rate among papers in the same bibliographic-coupling community.

## Baselines (no graph)

Venue retraction rate to T0; citation-count-independent size controls; authors with a prior
retraction (one-hop, i.e. a join). Graph signals must beat these to count, and the multi-hop
signals must beat their one-hop versions or the README says they did not.

## Metrics

AUPRC, precision@top-1% and top-5%, lift over the pool base rate, bootstrap 95% confidence
intervals, reported per T0 and per venue stratum.

## Known limitations (to repeat in the README)

- Retraction is a lagging, detection-driven label; mass retractions by one publisher can dominate.
- Retractions with no original DOI (5,952 rows in the source file) or not found in OpenAlex are
  invisible, so some pool venues labelled "no history" may have had retractions.
- The output is a statistical risk signal, **not** a finding of misconduct about any paper or person.

## Feasibility check (2026-10-15) - run before any model exists

First pool (40 H / 30 L / 33 Z venues, 300-3,000 works each, seed 42, `venues_v1` in DECISIONS.md)
was checked for how many *candidate-level* positives it can yield. Counts below are descriptive
diagnostics from the data, not model results.

| Pool | T0 = 2020-12-31 | T0 = 2022-12-31 |
|---|---|---|
| H (40 venues) | 84 positives | 8 |
| L (30 venues) | 0 | 2 |
| Z (33 venues) | 0 | 1 |

Findings and consequences:

1. **Positives live almost entirely in venues that already had retractions.** L and Z contribute
   essentially no positives; they act as low-risk negatives. Therefore the **primary result is
   reported within stratum H**, where the venue-history baseline is weakest; pooled numbers are
   secondary because pooling lets "is this an H venue?" do most of the work.
2. **Pool too small.** ~84 positives is too few for stable intervals. Enlarging H raises positives
   roughly in proportion to pool size (about 0.08% of candidate works at T0 = 2020).
3. **T0 = 2022 is dominated by a handful of venues.** Its positive count jumps from tens to
   hundreds when particular mass-retraction journals happen to enter the sample. It is reported
   only as a regime check, never pooled and never a headline number.
4. **Positives cluster inside venues** (mass retractions), so ordinary bootstrap intervals would be
   too narrow. Confidence intervals use a **venue-clustered bootstrap**.
5. T0 must be >= the selection cutoff (2020-12-31); earlier cutoffs would leak venue history.
   Valid cutoffs are therefore 2020-12-31 (primary) and 2021-12-31 (secondary).

Proposed revision (pending participant confirmation): H = 150 venues, same size cap and seed
family; L = 30 and Z = all size-eligible (33). Estimated ~218k works (all types) and ~167 / ~244
positives at T0 = 2020 / 2021. This change was made AFTER seeing positive counts; that is
disclosed here and venues are still chosen from pre-cutoff history only.

## Pool as built and loaded (2026-10-15)

Final pool (`venues.json`, seed 42): 213 venues = 150 H + 30 L + 33 Z (60 Z requested; only 33
passed the size filter). 251,645 journal articles (2017-2022, deduplicated by DOI) pulled with
`type:article`. Loaded into FalkorDB: 2,272,088 `Paper` nodes (312,108 held in full + 1,959,980
cited-only stubs), 261,595 `Author`, 6,834 `Venue`; 7,358,531 `CITES`, 825,078 `WROTE`,
310,198 `PUBLISHED_IN`. Counts were read back from FalkorDB and survive a container restart.
In memory: ~1.2 GiB (so the live demo must use a subset; the free cloud tier is 100 MB).

Candidate-level positives (computed in Cypher inside FalkorDB and independently from the staging
files; the two agree exactly):

| T0 | Candidates | Positives | Of which in H |
|---|---|---|---|
| 2020-12-31 | 167,584 | 140 | 140 (L = 0, Z = 0) |
| 2021-12-31 | 169,672 | 140 | 140 (L = 0, Z = 0) |
| 2022-12-31 | 169,371 | 484 | 481 (L = 2, Z = 1) |

**Positives are extremely concentrated in a few venues** (mass retractions of a batch of papers):

- T0 2020: 140 positives from 27 venues; the top venue holds 76 (54%), the top two 98 (70%).
- T0 2021: 140 positives from 20 venues; the top three hold 113 (81%).
- T0 2022: 481 positives in H, 425 (88%) from a single venue.

Consequences for how results may be reported:

1. The effective number of independent events is far smaller than the positive count. Intervals
   must use the venue-clustered bootstrap, and will be wide.
2. Every headline metric is also reported **excluding the single largest venue** and with a
   per-venue breakdown, so a result driven by one retraction batch is visible as such.
3. T0 2022 stays a labelled regime check only (one venue = 88% of positives).
4. A model that has not seen any member of a batch retracted before T0 cannot recognise the batch
   from retraction history alone; the community/co-citation signals have to carry that. Whether
   they do is what the backtest measures, and "no lift" is a possible honest outcome.
