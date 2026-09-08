# Recent actual model usage

None of these five recent comparisons establishes accepted overall token savings. This overview covers the two Django live-index caller comparisons and three completed saved-archive comparisons, not every historical pilot. Different tasks and runtime revisions prevent treating them as repeated controlled measurements of one implementation. All use the same Django source revision; they are not independent repository samples.

| Task | Baseline input | Graph input | Baseline output | Graph output | Acceptance problem |
| --- | ---: | ---: | ---: | ---: | --- |
| iri_to_uri | 69,777 | 110,525 | 5,280 | 8,313 | Both correct; more graph tokens |
| conditional_escape | 52,873 | 171,833 | 6,901 | 9,128 | Baseline citation failure; more graph tokens |
| capfirst archive | 221,419 | unknown | 10,499 | unknown | Graph timeout; baseline semantic omissions |
| urlencode archive | 379,707 | 555,486 | 12,594 | 13,297 | Graph fallback explanation wrong; more total tokens |
| safe redirect archive | 29,960 | 90,104 | 4,581 | 5,909 | Both correct; more graph tokens |

Input includes its cached subset. results.json retains cached and uncached counts separately, output/reasoning subsets, timing, command observations and source-result hashes. The one favorable uncached-input result (urlencode, 58,171 to 40,542) does not overcome its quality failure and greater total input/output. Missing timeout usage is unknown, never zero. No prices, token estimates or cross-task average savings are computed.

The source reports retain exact quality criteria and limitations: [iri_to_uri](../django-callers/REPORT.md), [conditional_escape](../django-html-callers/REPORT.md), [capfirst](../archive-capfirst/REPORT.md), [urlencode](../archive-urlencode/REPORT.md), [safe redirect](../archive-safe-redirect/REPORT.md). The collector verifies the usage arithmetic and hashes the saved result files; it does not independently regrade explanations or replay commands.

Functional evidence remains separate: complete versioned XZ archives, source-free graph querying, hash-verified source excerpts, scope/pagination and platform installation checks work on the recorded corpora. They establish available functionality, not model efficiency. The shortened skill entrypoint has no completed model result yet. The force_bytes baseline is currently running in its original declared trial, so it is deliberately absent from this completed-result table.

Completion still requires correct completed answers with lower actual usage, plus the open issue requirements. More fixture passes, fewer response bytes or a green platform matrix alone cannot satisfy that requirement.
