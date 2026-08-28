# Research data model

Every assessment has an explicit origin: `REAL`, `SYNTHETIC`, `DEMO`, or `TEST`. Filters never silently mix them.

Real-data inclusion requires all of the following:

1. organization/controller research consent;
2. affirmative research consent from every contributor whose responses affect the case;
3. completed assessment and frozen instrument version;
4. anonymized identifiers instead of direct PII.

Withdrawal excludes the case from future research datasets, statistics, exports and benchmarks. Non-real data is visibly labelled and may be exported for testing without being represented as real.

Benchmark cohorts use the latest eligible completed assessment per organization, the same instrument version and the configured minimum sample. Cells below the minimum return an unavailable reason without revealing the exact small count.

The Excel workbook contains the exact ten sheets documented in the UI. SPSS export is a reproducible ZIP containing `dataset.csv`, `codebook.xlsx`, `labels.xlsx`, `import.sps`, and `README.txt`. Generated artifacts are stored with SHA-256 fingerprints and downloaded from their immutable snapshot.
