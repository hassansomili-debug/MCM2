# Diagnostic and improvement engine

Diagnostics are deterministic rows tied to an instrument version. A rule declares affected dimension codes, an operator (`lt`, `gap_gt`, or `average_lt`), threshold, severity and confidence. The engine stores the matched rule and exact score evidence.

Gaps compare configured dimensions and appear only when the configured threshold is exceeded. Priorities use the stored weights for gap, impact, dependency, effort and confidence; negative gaps are clamped to zero. The output records rank, score and rationale.

Recommendations are versioned by dimension. Finalization materializes a 30/90/180-day roadmap with suggested owner, KPI, impact, effort, target date and status. Company admins can update owner/date/status; recalculation never overwrites a completed assessment's evidence, and a reassessment creates linked new evidence.
