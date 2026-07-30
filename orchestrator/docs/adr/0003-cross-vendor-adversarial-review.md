# Cross-vendor adversarial review, bounded at 3 rounds

When adversarial review is enabled, a work item that reaches the review state is reviewed by a **second worker running a different-vendor model** (e.g. implement with opus-5, review with gpt-5.6) — a different vendor is more likely to catch what the implementing model rationalised. The review model is named explicitly in config (`models.review`, with its own effort) and the orchestrator asserts its vendor differs from the impl model's.

The reviewer posts a verdict (approve / request-changes + findings). On request-changes the orchestrator re-prompts the **original impl worker** with the findings, then re-reviews — bounded at **3 rounds**. After an approve, or after the 3rd round regardless, the orchestrator gathers evidence and flips the item to **human review**. Merge is always a human step; the orchestrator never auto-merges.

## Considered Options

- **Cross-vendor reviewer, ≤3-round fix loop, then human** (chosen) — automation catches obvious defects, the round cap prevents an infinite bounce, and the human still owns the merge decision.
- **Auto-pick opposite vendor** — rejected in favour of an explicit `models.review` for predictability.
- **Same-worker self-review** — rejected: same model, not adversarial.
- **Unbounded loop / auto-merge on approve** — rejected: no ceiling on cost, and removing the human merge gate is too much trust.

## Consequences

During the loop the item stays `in-progress` (a worker still owns it); no new tracker label is invented. Config carries `review.enabled` and the round cap (default 3); the reviewer's model + effort come from `models.review` (see ADR-0005). Each fix round steps the impl worker's effort up one rung. The reviewer is prompted for **coverage, not self-filtering** — current models obey a "only high-severity" bar literally and drop real bugs.
