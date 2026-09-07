# Qualified method lookup in portable archives

A generated archive exposed a real ordering omission: querying Loader.getResource with limit two returned a.OtherLoader.getResource and b.Loader.getResource, excluding c.Loader.getResource. Archive search ranked every substring alike, unlike the newly improved SQLite route. The preserved failing test output records that mismatch.

Archive search now ranks component-boundary qualified suffixes between full exact matches and general substrings. Both genuine Loader declarations appear before OtherLoader, while a full exact name still selects OtherLoader. The final regression query runs after its temporary source repository and SQLite have been removed, and creates no new consumer files. Archive serialization is unchanged.

Both parser engine suites pass 211 tests; root tests pass 53. The existing 5,009,364-byte Spring archive is also queried from an empty directory in 1,890 response bytes under a 2,048-byte cap. Its SHA-256 stays unchanged; the response retains snapshot freshness, source hashes, semantic incompleteness and truncation. See spring.json for the exact receipt. This is bounded declaration navigation, not source-free relationship traversal or a model-token savings result.
