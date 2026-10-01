# Classification and review rules (1.1.0)

Each category is an independent yes/no question: category scores do not sum to 100%. High scores for two genres can therefore support assigning both.

A result is ready only when there is meaningful source material (a description of at least 200 characters or actual excerpts), JEV evidence confidence is at least 80%, and the assignment rules below pass. Requesting excerpts explicitly but receiving none requires manual review. Automatic mode can accept sufficient metadata alone.

The default assignment threshold is 85%. Enabled categories can override it individually. The closeness margin defaults to 8 percentage points and includes the boundary. Scores must strictly exceed 50% to qualify. Threshold comparisons use the original score, not the rounded percentage shown in the interface.

| Scores | Multiple tags | One tag |
| --- | --- | --- |
| 90%, 88% | Both ready | Highest suggested; manual choice required |
| 90%, 84% | Only 90% ready; 84% optional | Manual choice required |
| 90%, 82% | Only 90% ready | Manual choice required (8-point boundary) |
| 90%, 81% | Only 90% ready | Highest ready |
| 80%, 79% | Both review-only suggestions | Highest review-only suggestion |
| 50%, 49% | No automatic suggestion | No automatic suggestion |

These examples assume sufficient evidence and the default threshold for both categories. In multiple-tag mode, proximity never bypasses a category threshold. Excluded alternatives do not prevent applying qualifying categories. In single-tag mode, a likely alternative within the margin blocks readiness even if that alternative is below its own threshold.

Review reasons distinguish missing material, low evidence, no likely category, below-threshold suggestions, a single-tag near tie, and unavailable requested excerpts. Low evidence produces no preselected tags. The detail panel still allows an explicit manual choice among configured categories.

Single-book classification opens the tag panel directly. Batch classification keeps a list, status filters, and per-book details. Low-scoring categories are hidden until requested. Clicking a tag only changes the local selection. Confirming batch details marks the book verified and selects it for application; closing details does neither. Single-book confirmation applies tags, or stages them in the metadata editor until its OK button is pressed. Existing tags are preserved.

Ready status permits automatic application only when the user enabled that option. Review-only suggestions are never automatically applied. CSV export retains machine suggestions separately from user choices. Existing cached JEV responses are evaluated under current rules without altering their recorded probabilities.
