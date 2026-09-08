# Prospective Express download/transfer source review

This is a new operation on a previously used repository, not a held-out repository. The earlier Express cohort concerned rendering; its answers and rubric are not pass criteria here. This review and the six findings were prepared before any trial for this task. All 23 semantic clauses are mandatory; there are no partial-credit substitutions. The visible question and finding descriptions request every scored behavior. Paths, markers, line controls and this review are private evaluator inputs, not model instructions.

## Corpus and boundaries

The source is Express commit `023767fe9872e029271df1418f73401bff20ff40`, [official commit](https://github.com/expressjs/express/tree/023767fe9872e029271df1418f73401bff20ff40). The pre-existing full local snapshot ZIP and its provenance are recorded in `source.json`. All 213 files, totaling 713,745 uncompressed bytes, were compared byte-for-byte with the existing source directory. The archive contains the full scoped repository snapshot, not only selected implementation excerpts. Its original download transaction was not observed in this preparation; the historical local metadata associates it with the commit. No new download, model call, repository execution or dependency installation was performed.

The operation resides in `lib/response.js`. The public methods and private helper were read in full, including imports, and relevant tests were inspected as corroboration without running them. The ZIP does not include installed `send`, `on-finished` or `content-disposition` implementations. Claims stop at their calls and the local event/closure logic; Node filesystem/HTTP internals, containment, range/cache/MIME behavior and particular network timing are not required. The task explicitly excludes exotic/proxy/getter/frozen options, unsupported download combinations and throwing callbacks/header operations. Standard JavaScript object inheritance, truthiness and callback flow are in scope.

## Clause-by-clause oracle

Clause numbers below are zero-based indices in `criteria.json`. Each finding may quote one representative contiguous range of at most 40 physical lines; explanations must cover the remaining inspected branches. A correct quote can establish code it actually contains when prose omits that detail, but cannot establish absent cross-range behavior. Contradictory prose fails even alongside correct code. Do not force a whole helper or stitched cross-range quotation into the citation.

### download_arguments — four clauses

- 0: `lib/response.js:435–438` initializes fourth-position callback, filename and `options || null`.
- 1: `441–448` handles a second-position callback by clearing both name and options, or a third-position callback by clearing only options.
- 2: `450–455` accepts the second-position object only when the third position is a function or undefined. It preserves the callback normalized above. Do not broaden this condition to every object filename.
- 3: `477–483` computes the final path and returns the public `this.sendFile(fullPath, opts, done)` delegation. That local call is source evidence even if a heuristic graph omits its receiver relationship.

Representative citation control: `435–455` (21 lines), containing the object-position normalization marker. No particular call line is required for this normalization quote. `test/res.download.js:20–91, 151–187, 358–426` corroborates the documented callback and options forms.

### download_options — four clauses

- 0: `457–460` applies `contentDisposition.create(basename(name || path))`. The alternate name affects attachment naming only; the original path remains the source input at `478–480`. Empty alternate names fall back through ordinary truthiness.
- 1: `462–471` enumerates own header keys with `Object.keys`, rejects any case spelling of Content-Disposition and copies other keys/values without renaming.
- 2: `473–475` uses `Object.create(opts)`, then a fresh own headers property. This is prototype inheritance, not spread/copy; null defaults produce a null-prototype object. With the ordinary data objects in scope, the original options and headers are not written by these branches.
- 3: `477–480` resolves the original path only when root is falsy, otherwise passes it unchanged. This does not establish external containment behavior.

Representative citation control: `457–484` (28 lines), including derived options and the required delegate call at 483. `test/res.download.js:189–286, 408–463` corroborates header forwarding/protection. Missing-file tests do not justify a universal no-headers-after-any-error claim.

### sendfile_setup — four clauses

- 0: `373–395` checks falsy path before non-string type, then rejects a relative path without truthy root. These TypeErrors precede stream setup and are not caught here.
- 1: `374–391` starts from `options || {}` and replaces a second-position function with a callback plus fresh options. A supplied ordinary options object is otherwise retained by reference.
- 2: `398–403` encodes the path and assigns app-controlled `etag` before the imported send call. That assignment writes direct options, while download's derived options object keeps the original options untouched (`474–475`). No dependency-specific ETag or encoding algorithm is scored.
- 3: `403–406` separates imported `send(req, pathname, opts)` construction from local lowercase `sendfile(res, file, opts, closure)` transfer wiring. Import identities are at `15, 21, 24, 31, 33–34`; unavailable dependency implementation is outside the oracle.

Representative citation control: `373–403` (31 lines), including the required stream-construction call at 403. `test/res.sendFile.js:22–116` corroborates validation, special-character handling and application ETag configuration; the broader HTTP assertions are not additional clauses.

### callback_routing — three clauses

- 0: `406–407` returns the supplied callback before automatic routing, on success and errors alike. This closure neither sends a response nor checks `headersSent`; these remain callback responsibilities.
- 1: `408–413` maps EISDIR to `next()` without an error, suppresses default forwarding for ECONNABORTED and write-syscall errors, and forwards other errors. No truthy error means no next call. Downstream status generation is not shown here.
- 2: `373–406` has no setup try/catch. A synchronous validation/setup throw before the helper call does not turn into a completion callback. Do not enumerate uninspected dependency exceptions.

Representative citation control: `406–414` (9 lines), including callback precedence at 407. `test/res.sendFile.js:147–280` and `test/res.download.js:465–487` corroborate callback success, abort and missing-file error handling; they do not prove all possible transport sequences.

### transfer_events — four clauses

- 0: `987–1008` registers the five file listeners, response-finish listener and optional headers listener before piping. An event registration is not itself a resolved callback call edge or a promise about external event emission.
- 1: `921–956` initializes `done` false and guards/set-before-callback in abort, directory, generic-error and end handlers; `965–979` applies the same completion protection during finish handling. Reentrant or repeated terminal notifications cannot complete again under the task assumptions.
- 2: `925–956` synthesizes ECONNABORTED and EISDIR, forwards original generic errors and reports successful end with no argument.
- 3: `994–1004` reads the current headers object and enumerates/setHeaders inside the optional headers event, not eagerly at setup. This helper contains no error rollback/removal. A failure before that event does not set headers through this listener, but an error after it does not erase them.

Representative citation control: `987–1009` (23 lines), including pipe at 1008. The quote deliberately represents wiring rather than pretending to contain all earlier terminal handlers. `test/res.sendFile.js:509–585` corroborates headers on transfer and their absence for a missing-file case only.

### finish_race — four clauses

- 0: `923, 959–962, 982–985` makes streaming initially undefined, false after file and true after stream.
- 1: `965–968` maps ECONNRESET through abort synthesis, forwards other errors through onerror and respects prior completion through those guarded handlers or the direct done check. The original reset error is not the callback error produced by the abort branch.
- 2: `970–974` defers the non-error check with setImmediate and uses the latest flag/done values. Both undefined and true satisfy `streaming !== false` and cause abort if still unfinished.
- 3: `976–979` skips an already completed transfer; otherwise the false-streaming branch marks done and reports success. An intervening end/error/abort notification prevents a second completion. This is source-level control flow, not an asserted actual network schedule.

Representative citation control: `965–980` (16 lines), including at least one recorded call line 972 or 978. The neighboring small handlers must still be inspected to explain flag transitions and error identity.

## Independent relationship controls and quote adoption

Useful relationships must be observed as actual stored edges and checked against source. Quote extraction or declaration retrieval alone is not graph evidence. Read-only inspection of the existing historical archive `graph.jsonl.xz` (identity in `source.json`) found these source-supported heuristic calls:

| Caller | Target | Physical line |
| --- | --- | --- |
| `lib/response.js::sendFile:function` | `lib/response.js::sendfile:function` | 406 |
| `lib/response.js::sendfile.onfinish:function` | `lib/response.js::sendfile.onaborted:function` | 966 |
| `lib/response.js::sendfile.onfinish:function` | `lib/response.js::sendfile.onerror:function` | 967 |
| `lib/response.js::sendfile.onfinish:function` | `lib/response.js::sendfile.onaborted:function` | 972 |

The historical graph did not record download's `this.sendFile` call at 483; do not fabricate a resolved edge. Its nodes/edges are heuristic, not semantic proof. Before the prospective freeze, regenerate/validate controls against each arm's actual full-source archive. Suitable bounded probes are `archive-callers 'lib/response.js::sendfile:function'` and `archive-neighbors 'lib/response.js::sendfile.onfinish:function' --direction out --kinds calls`, with explicit input/repository, bounded context and byte budget. Event-listener registrations and external imports are not substitute resolved call targets.

Optional `archive-quotes` can obtain an already selected representative range. Adoption is a separate trace observation and cannot satisfy relationship use. No command is required merely to improve a utilization score; ordinary bounded reads remain valid. Source equality or fewer serialized bytes than richer declaration batches is not full semantic equivalence, actual token savings or a gate result. The baseline must remain free to batch efficient searches and exact source reads. This task includes real navigation and state/error reasoning, but because most mechanisms occupy one file, it may offer limited graph savings; that is a prospective risk, not a reason to loosen the all-pair quality/input/output gate.
