# Prospective Axios interceptor-execution review

This is a predeclared source-navigation rubric, not a model result or an acceptance report. It was prepared by reading source and the existing saved-callers citation grader; no Axios code, tests, build, network request through Axios, or model trial was executed. The source ZIP was downloaded and inspected in memory. The cohort must still freeze its complete source snapshot, runtime, cases, criteria and protocol before any model execution.

## Source and scope

Repository: `axios/axios`. Commit: `e5a33366d75b65f88052b230b103731eb7dcb793`, the peeled commit of annotated tag `v1.12.2`. The tag object `4150efd104826d7af27d014378bf874964aa26ff` is not the source commit.

Full snapshot: <https://codeload.github.com/axios/axios/zip/e5a33366d75b65f88052b230b103731eb7dcb793>. Its SHA-256 is `c53e20043fc22e23f2b8a47d12a68dac007a71c3f9ae652d3188ceb4ba2b2345`, with 746,720 ZIP bytes and 242 regular source-snapshot files. The task selects a bounded behavior within that complete snapshot; the fixture must not be reduced to the cited files or snippets.

Reviewed files and SHA-256:

| Repository-relative file | SHA-256 |
| --- | --- |
| `lib/core/Axios.js` | `c00e716e4d26694a09e010b9837524a5d661659e6eaad2cbaa5b4304f6ab1a39` |
| `lib/core/InterceptorManager.js` | `7769d227806714491cd5d641041746dc073300df2e39c6709f59a4e766c18c15` |
| `lib/utils.js` | `b21b7010034f4b47a30e840df9deaa4067b9f0066c648bc04116f30266369850` |
| `LICENSE` | `82761059eaedacb3356803aea8a170d8298609f91b14fc32ee1bfb40d690183c` |

Authoritative implementations: [Axios request assembly](https://github.com/axios/axios/blob/e5a33366d75b65f88052b230b103731eb7dcb793/lib/core/Axios.js), [interceptor manager](https://github.com/axios/axios/blob/e5a33366d75b65f88052b230b103731eb7dcb793/lib/core/InterceptorManager.js), and [array iteration](https://github.com/axios/axios/blob/e5a33366d75b65f88052b230b103731eb7dcb793/lib/utils.js). Axios carries the MIT license in the full fixture.

The question assumes ordinary handler records, callable fulfilled handlers, valid configurations, non-throwing `runWhen` predicates and no registration mutation during request construction. On the direct path, successful fulfilled handlers return configuration objects. Rejection callbacks are deliberately not assumed to exist or succeed. These assumptions bound the task; they do not assert validation or safety guarantees in Axios.

The task includes manager storage/removal, request/response chain construction, the direct loop, Promise chaining and the public async request rejection boundary. It excludes adapter/transport behavior, configuration-merge and transformation internals, exact error-stack formatting, dynamic mutation of the manager during traversal, and arbitrary corrupted records or property getters. No source review should infer a deployed application's particular callbacks or network behavior.

## Citation and semantic contract

All five finding IDs must appear exactly once. Every clause in `criteria.json` is mandatory and corresponds to an explicit subject in the question or its finding descriptions. Equivalent correct wording is accepted. Supporting quoted code can establish a detail omitted from prose, but a cited range without an actual supporting quote is not itself an explanation. Shared context may appear in another finding; contradictory prose anywhere fails the affected semantics even if correct code is quoted elsewhere.

Keep the harness's unchanged source-relative path, physical line-number, at-most-40-line, contiguous verbatim quotation rule (indentation ignored). A representative quotation does not have to contain every supporting branch. The explanation may synthesize other inspected declarations; it must not stitch distant source excerpts into one alleged quote. The private path/marker fields in `cases.json` locate a representative mechanism and are not the whole semantic oracle. They must stay out of the model-visible prompt: the saved-callers harness renders only the question, finding IDs and descriptions.

The following ranges are possible pre-model citation controls, not required exact ranges for answers. They contain the corresponding private marker and fit the existing grader. No model receives this table.

| Finding | File | Representative physical lines | Line count |
| --- | --- | --- | --- |
| `registration_removal` | `lib/core/InterceptorManager.js` | 18–26 | 9 |
| `eligibility_order` | `lib/core/Axios.js` | 132–148 | 17 |
| `promise_path` | `lib/core/Axios.js` | 154–166 | 13 |
| `synchronous_errors` | `lib/core/Axios.js` | 171–188 | 18 |
| `response_boundary` | `lib/core/Axios.js` | 184–197 | 14 |

The exact control marker lines are respectively 25, 142, 163, 179 and 194. A model may choose another valid bounded range containing the marker. Registration's removal/iteration branches and the public request wrapper need not be packed into the representative quote; their requested semantics still require support in the answer.

## registration_removal

Primary source: `InterceptorManager.js:18–26`, `35–50`, `62–68`; array traversal at `utils.js:261–280`.

1. `use` appends the callback/options record and returns its array index. No options stores `synchronous=false` and `runWhen=null`; missing `synchronous` does not enable the direct mode. With an options object, the supplied properties are retained rather than normalized to a new true default. An answer need not distinguish null from undefined sentinels if its described default behavior is correct.
2. `eject` nulls an existing slot, preserving the positions/IDs of other handlers. New registrations append after the current array length rather than reusing the null slot. An already empty/absent ordinary slot is a no-op.
3. `clear` replaces the array with an empty one, allowing index zero and subsequent IDs to be reused. IDs are not globally unique across clears.
4. `forEach` skips nulls. The shared utility traverses an array in increasing index order, so surviving records remain in registration order and removed records do not participate in execution-mode selection.

The `eject` documentation advertises a Boolean return, but the implementation has no explicit return. Exact removal-method return values are not requested or scored; an unsolicited claim of a returned success Boolean contradicts the shown implementation and must not be endorsed.

## eligibility_order

Primary source: `Axios.js:132–148`; preparation precedes this block, and fulfilled execution occurs at `154–182`.

1. All request eligibility checks occur during assembly, before request fulfilled callbacks execute. Predicates receive the prepared configuration at that stage, not successive fulfilled-handler results.
2. Filtering requires a function returning the Boolean false. Other falsy returns are not excluded by the strict comparison. Missing/non-callable predicates do not filter handlers.
3. The accumulator starts true and combines only retained request handlers' `synchronous` values. Any missing/falsy value selects the Promise path; skipped/ejected asynchronous records do not vote. No retained request handlers keeps the direct path.
4. Prepending request pairs reverses registration order. Appending response pairs preserves it. Neither response `runWhen` nor response `synchronous` participates in this selection or filtering.

The question assumes predicates do not throw and registration does not change during construction. There is no requirement to analyze side-effectful predicate mutation, exotic records or concurrent changes.

## promise_path

Primary source: `Axios.js:154–166`, with chain order established at `132–148`.

1. The falsy-accumulator branch starts from a resolved configuration promise and attaches request pairs, dispatch, then response pairs. The callbacks are Promise stages, not calls through the direct request loop.
2. Fulfilled return values flow forward, including adoption of returned promises. Throws and rejected returns move later stages into rejection.
3. The rejection callback passed alongside a fulfilled callback to the same `then` does not catch that fulfilled callback's throw. A later applicable rejection callback can handle it; fulfilled callbacks are skipped while rejection persists.
4. A successful rejection callback recovers subsequent fulfillment; another throw or rejected return preserves rejection. Valid request-side recovery can reach dispatch. Otherwise dispatch's fulfilled stage is skipped, with a later response rejection callback still able to run.

These are consequences of the shown ordinary Promise chain. Do not claim that callback pairing implements the direct loop's same-handler catch behavior here.

## synchronous_errors

Primary source: `Axios.js:169–188`; public async wrapper at `38–63`.

1. Fulfilled callbacks run directly and each successful result replaces `newConfig`. The stated task assumption excludes success values that are not configuration objects on this path.
2. A thrown fulfilled callback invokes its own rejection callback with the Axios receiver and the error. A normal return is ignored; the `break` skips every remaining request handler rather than resuming or accepting that return as configuration.
3. Dispatch is then attempted with the last successfully assigned configuration. A throwing assignment never completes, but existing-object mutations are not rolled back, including mutations through a rejection callback's closure.
4. A missing/non-callable or throwing rejection callback escapes before dispatch/response attachment. `_request` can throw synchronously; the public `async request` wrapper ultimately rejects. Exact stack augmentation is outside the task, but treating the public API as successfully continuing is wrong.

Do not conflate two outcomes: a normally returning rejection callback permits dispatch with the surviving config; a failed rejection callback prevents it.

## response_boundary

Primary source: `Axios.js:184–197` and `154–166`; public wrapper at `38–63`.

1. A normally returned dispatch promise receives response pairs in registration order in both modes. If that promise rejects later, response rejection callbacks can run even when request callbacks were synchronous.
2. The direct path catches a synchronous dispatch throw and returns a rejected promise before response attachment. The public call rejects, without these response handlers receiving that early-return error.
3. The Promise path already includes response stages after dispatch. A synchronous dispatch throw becomes a chain rejection and can reach them; it does not take the direct path's early-return branch.
4. Response values, errors and recoveries follow ordinary `then` rules. A callback's throw goes downstream, not to its own paired rejection callback. The final chain controls the public result/rejection; recovery is not guaranteed for absent or failing callbacks.

The task treats dispatch as the shown call boundary. No answer must enumerate adapters, trigger an HTTP request, simulate callback execution, or inspect all transform/cancellation branches to establish these control-flow distinctions.

## Freeze and review notes

These files do not authorize model execution and are not frozen solely by existing on disk. Before launch, independently review each clause, verify positive/negative citation controls on the full fixture, and hash the completed protocol inventory. The five findings preserve the requested semantic boundaries; small output or mechanically valid citations cannot replace them.

The prospective cohort retains all six pair requirements, including full citation/semantic quality and strictly lower actual input and output per pair. This saved-archive task can observe useful archive retrieval and compact/batched delivery, but not local receipt-backed continuation. Historical failed cohorts and their graders remain unchanged.
