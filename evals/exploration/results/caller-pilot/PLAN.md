# Predeclared direct-caller comparison

Use the frozen c67b20a runtime fixture and caller-cases.json, whose exact sites are independently reviewed in evals/caller-corpus. Ask for all direct callers of index.compact without revealing the expected names or count. Ground every caller in an actual call-site range and contiguous verbatim quote. The automated gate rejects missing, duplicate, extra callers, wrong files and citations outside reviewed call sites; inspect explanations separately.

One baseline trial followed by one Columbus trial; repeat 1, requested gpt-5.6-sol, xhigh, 600 seconds each. Freeze the current engine and reduced skill before either trial. Both arms get identical task/citation instructions. Columbus may use its prebuilt graph or ordinary search; no forced graph use. Preserve all failures, raw event hashes and actual runtime usage; no selective reruns. Read-only source, no execution of repository code, no web or delegation inside model trials.

This is one caller-enumeration pilot, not a repeated-session experiment or general token-saving claim. Only interpret savings if both answers pass exact-set/citation and semantic review, settings/source match, and graph invocation evidence supports the claimed mechanism. Cached input is a subset of input; do not infer billing savings. Results are pending at predeclaration.

Execution completed after predeclaration. See REPORT.md and controlled.json; both answers pass but efficiency regresses. No selective reruns were performed.
