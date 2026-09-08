# Predeclared Express render-pipeline criteria

Source: expressjs/express commit `023767fe9872e029271df1418f73401bff20ff40`. `source.json` records the reviewed file hashes and exact citation markers. This catalog and review were prepared before model execution; no application, template engine, tests or model were run during preparation.

The task is one end-to-end source-navigation question, split into six findings for review. It follows `res.render`, `app.render`, the default built-in `View` constructor, `lookup`, `resolve`, `render`, `tryStat`, and application `tryRender`. The application can configure another View class and engines are external callbacks; these source declarations do not prove which implementation any deployed app uses. The built-in default is assigned in `app.defaultConfiguration`.

All six semantic findings must pass. Each required behavior below must be established by correct prose or an actual supporting source quotation; an oversized citation range by itself is not an explanation. Equivalent wording is accepted. Related findings can supply shared context, but a contradictory claim anywhere cannot be repaired by quoting correct code elsewhere. Require the harness's unchanged repository-relative, contiguous verbatim citation rule. One bounded quotation need not contain every supporting branch; the explanation may synthesize the other inspected source. The exact marker controls citation location, not all semantic correctness.

## response_delegation

Primary source: `lib/response.js:894–918`.

- `res.render` gets the application from `this.req.app`. Missing/falsy options become an empty object; a function in the options position becomes the callback and uses empty options.
- It assigns `opts._locals = self.locals` before delegating. This carries response locals and overwrites a caller-supplied `_locals` property on that options object; it is not a deep merge or a cloned options object here.
- With a supplied callback, Express passes that callback through and does not automatically send the rendered response. Without one, the default callback sends the string with `self.send(str)` on success and returns `req.next(err)` on error; it does not send after the error branch.
- It calls `app.render(view, opts, done)`. Do not claim `res.render` itself selects files or invokes the engine directly, or that supplying a callback still triggers the default response send.

## locals_and_cache

Primary source: `lib/application.js:522–575`; the setting default is at `lib/application.js:90–140`.

- `app.render` also supports the callback as its second argument and uses empty options for missing/falsy options. It constructs a fresh, shallow render-options object in this order: application locals, `opts._locals`, then explicit `opts`. Later own properties override earlier ones. Thus through `res.render`, explicit options take precedence over response locals, which take precedence over application locals; nested values are not recursively merged.
- The cache decision is made from the merged `renderOptions.cache`. Only a null/undefined value (`== null`) is replaced by `this.enabled('view cache')`. Explicit false disables the cache and is not overwritten. The normal configuration enables view cache in production; the render function itself consults the current setting, rather than assuming caching is always on.
- When the resulting cache value is truthy, lookup uses `this.cache[name]`. A cached View is reused, bypassing construction and path lookup for that request. With caching disabled or a miss, `this.get('view')` supplies the configured constructor and receives the default engine, configured views root(s), and shared engine registry.
- A newly constructed View with a resolved path is inserted under the original render name only when caching is enabled. This insertion occurs before `tryRender` invokes rendering. A rendering error does not have a cache-eviction branch here. A failed path lookup returns before insertion.
- This cache stores a View object, not rendered HTML and not a per-locals result. Reusing it still renders with the current merged options. The engine registry is a separate reuse mechanism; do not equate a false View-cache option with reloading every engine.

## engine_selection

Primary source: `lib/view.js:52–95`.

- The constructor derives the extension from the supplied name. An existing filename extension selects that engine key instead of appending or overriding it with the default engine.
- Without an extension, a default engine is required. The constructor normalizes a missing leading dot on the default engine, appends the resulting extension to its lookup filename, and throws if neither an extension nor a default exists.
- It first consults the shared `opts.engines` registry by extension. A truthy registered entry is reused. On a miss it requires the extension's module name without the leading dot, selects `.__express`, requires that export to be a function, and stores it back under the extension. Missing modules can throw from `require`; a non-function export raises the explicit view-engine error. Do not claim every render requires the module again or that every export shape is accepted.
- The engine is selected/loaded before `this.lookup(fileName)` determines `this.path`. The function later calls this selected engine; code inspection does not execute or prove the external engine's behavior.

## view_lookup

Primary source: `lib/view.js:104–123`, `169–205`; caller's missing-path branch at `lib/application.js:558–565`.

- Lookup converts the configured root or root array into an array and tries roots in order, stopping at the first truthy resolved path. It resolves each root/name pair and splits its directory and basename before calling `this.resolve`.
- In each root, resolution tries the named file first and then the sibling directory's `index` plus the selected extension: for example, `foo.ext` precedes `foo/index.ext`. A later root's direct file does not outrank an earlier root's successful index fallback.
- Both candidates must produce a stat object for a regular file (`isFile()`). A directory alone is not accepted. `tryStat` catches stat failures and returns undefined; a failed direct candidate can still reach the index fallback, and a failed root can still reach the next root.
- Exhausting candidates leaves the path undefined. This is the unsuccessful result that `app.render` turns into its missing-view callback error. Do not claim the lookup helper itself throws on a normal missing file, searches all roots and picks the last match, or treats an arbitrary directory as a renderable file.

## error_boundary

Primary source: `lib/application.js:549–574`, `625–631`; response default handling at `lib/response.js:910–917`.

- A constructed View without a path produces an Error describing the failed name and configured root(s), attaches that View as `err.view`, and returns `done(err)` before cache insertion or rendering. Exact punctuation of the error message is not a semantic requirement.
- `new View(...)` occurs outside `tryRender`'s try/catch. The built-in constructor's missing-default-engine error, module-load failure and invalid-engine-export error can therefore throw synchronously out of `app.render`; do not say every construction/lookup failure is converted to the callback by `tryRender`.
- `tryRender` wraps the call to `view.render(options, callback)` and converts a synchronous throw from that call to `callback(err)`. It does not wrap an entire future asynchronous engine execution or guarantee asynchronous delivery of caught errors.
- An engine's normal error callback is forwarded through built-in View's callback adapter. The default `res.render` callback sends errors to `req.next`; a supplied callback owns its error handling. Do not claim the default sends an error string as successful HTML or that the wrapper catches arbitrary later asynchronous throws.

## callback_timing

Primary source: `lib/view.js:133–159`; `tryRender` at `lib/application.js:625–631` supplies the synchronous-throw boundary.

- Built-in `View.render` calls the selected engine with the resolved path, current options and an `onRender` callback. The local `sync` flag starts true and changes to false after the engine invocation returns normally.
- If the engine invokes its callback before returning, `onRender` copies its arguments and saves its receiver, then schedules the user's callback with `process.nextTick`. Arguments and callback receiver are preserved; it does not invoke the user callback inline on that synchronous engine-callback path.
- If the engine callback arrives after the engine invocation returned, the false flag forwards it immediately through `callback.apply(this, arguments)` in that later callback invocation, without adding another nextTick.
- This is timing normalization, not a once guard. The shown implementation does not suppress repeated engine callbacks and cannot guarantee at-most-once delivery. A synchronous callback followed by an engine throw can also leave a scheduled callback while `tryRender` reports the throw; giving this example is optional, but asserting an unconditional once guarantee fails.
- Do not generalize this to saying every error is asynchronous: the missing-path branch and `tryRender` catch can call back immediately, and constructor failures can throw. A custom configured View can bypass the built-in normalizer.

## Boundaries and review controls

The required precedence, cache timing, root/file search order, throw/callback boundary and absence of a once guard are part of the question, not optional embellishments. The reviewer must check them before accepting a token-saving result. A smaller response or a syntactically valid quote cannot substitute for them.

The question does not require an exhaustive Express middleware trace, `res.send` content-type/status internals, every app-setting inheritance detail, Node event-loop ordering beyond the shown nextTick choice, a template engine's internals, rendering safety/security claims, or a proof from executing a deployed app. A callback's receiver is preserved as supplied by the engine; its concrete identity cannot be fixed from these declarations alone.

Supporting tests in `test/app.render.js` and `test/res.render.js` were read for cache reuse, options precedence, callback ownership and ordinary error examples. They were not run and do not establish universal engine callback behavior. No mandatory criterion depends on a third-party dependency implementation or unrecorded runtime experiment.
