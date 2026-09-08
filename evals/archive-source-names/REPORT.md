# Consistent declaration selection for source reads

The second Requests observation attempted import-like names with archive-source, although the command required exact IDs. This differed from archive-callers, which already accepted unique names. Source reads now use the same rank helper as caller reads: exact ID, exact name/qualname or recorded Python module.qualname, then a unique case-sensitive qualified suffix at a dot boundary. Ambiguous best-ranked candidates fail after complete archive validation. Wrong declaring owners are not guessed or redirected through inheritance.

The result target is always the selected exact ID, so the existing packet and source-line pagination are preserved. Source retrieval still validates the whole archive in one pass and checks the full local file hash. No archive schema, graph edges or runtime dispatch claims change. The skill documents the shared name rules and directs unknown-owner cases to search.

Added tests failed before implementation and now pass for gzip/XZ, exact and suffix names, ambiguity, false boundaries/case/owners, exact-name precedence, exact-ID precedence and unordered records. All 250 engine tests passed under the ordinary and experimental Java environments; root checks passed 53. Skill validation and wheel/ZIP verification passed. Existing caller regressions pass using the shared selector.

On the frozen Requests archive, requests.sessions.Session.send now returns the identical source packet as its exact ID. The unique name resolve_redirects also returns the same packet as its real SessionRedirectMixin declaration. The two observed wrong-owner queries still fail; this change only removes the name-vs-ID mismatch, not every retry. Replay details are saved in replay.json. No model was called and no actual token savings are claimed. The completed ten-pair overview and all frozen trial inputs remain unchanged.

CI 34188875111 at 3192cb1 passed all six Linux/macOS/Windows and Python 3.11/3.14 environments. The complete receipt is platform-final.json.
