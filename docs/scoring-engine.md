# Scoring engine

`mcm/scoring.py` is the only authority that creates scientific scores. The browser sends raw answers only.

For a numeric item with scale bounds `min` and `max`:

```text
normalized = (answer - min) / (max - min) * 100
reverse-coded = 100 - normalized
```

Multiple respondent values are averaged per item, then each dimension is the weighted mean of its answered item scores. A construct total is the weighted mean of its dimensions. MCM uses the seven `MCM*` dimensions only; SMCE uses the five `SMCE*` dimensions only. Enablers and optional outcomes never enter the MCM denominator.

Explicit missing states are `NOT_ANSWERED`, `NOT_APPLICABLE`, `SKIPPED`, and `TECHNICAL_MISSING`. They do not become zero and do not enter the answered denominator. Required items must be answered by each submitting participant.

Every final calculation creates an append-only `score_runs` record containing the instrument version, scoring method, configuration snapshot, response input hash and output hash. Current materialized score tables can be rebuilt; prior score-run evidence is retained.

The bundled maturity boundaries are provisional configuration for Research Beta. Only MCM receives one of five labels: `REACTIVE`, `RESPONSIVE`, `MANAGED_INTEGRATED`, `PROACTIVE_ADAPTIVE`, or `INSTITUTIONALISED_INTELLIGENT`. They are not a validity claim.

After calculating both constructs, the response also reports `SMCE - MCM` and one deterministic alignment interpretation. This is a descriptive diagnostic bridge between the constructs. It does not change either total and is explicitly marked `PROVISIONAL_ASSOCIATION_NOT_CAUSAL` until quantitative testing supports the proposed positive effect.
