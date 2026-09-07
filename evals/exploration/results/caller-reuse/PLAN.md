# Predeclared verified-excerpt reuse comparison

Use the unchanged c67b20a source fixture, caller-cases.json and current engine. The only intended change is the revised skill: callers is the first query for direct-call tasks, verified excerpts can be cited directly, and remaining independent import/coverage checks are batched. One fresh Columbus trial then one fresh baseline trial, requested gpt-5.6-sol, xhigh, repeat 1, 600-second timeout. Freeze the engine and skill before running. No selective reruns; retain previous unfavorable observations.

Both answers must pass exact caller-set, contiguous quotation and source-based semantic review. Compare total input, cached subset, uncached input, output, elapsed time and command-output bytes. Record whether returned excerpts are reused and graph/query positions. Source/settings must match; skill-loading cost is included. One pair does not prove general or repeated-session savings. No source writes, target code execution, web or delegation inside model trials.

Execution completed; both quality gates pass, but usage regresses. See REPORT.md and controlled.json. No trials were discarded.
