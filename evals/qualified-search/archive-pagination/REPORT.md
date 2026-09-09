# Continue bounded archive relationships

archive-neighbors previously reported omitted edges but provided no way to read beyond its 50-edge cap. It now accepts --offset and returns next_offset. The cursor advances only over returned edges, including when byte trimming reduces a page. Consumers keep the same artifact, ID, direction and kinds; a changed revision requires restarting. A budget too small for even one matching edge fails rather than returning a non-progressing cursor.

Generated tests read 65 distinct incoming calls under a 2,048-byte response cap with no duplicates or omissions, cover negative/out-of-range offsets, and preserve self-loop/direction behavior. Both engine suites pass 213 tests, root tests pass 53 and skill validation passes.

A real source-free Spring CLI observation reads the six saved getResource call edges in three pages of two edges under 3,500 bytes each (3,013 / 2,756 / 2,796 bytes). Concatenated edge rows equal the complete response; no consumer files are created and the archive hash remains unchanged. [Raw receipt](spring.json).

The final page can retain truncated=true because earlier edges were skipped; next_offset=null is the continuation terminator. Each page still scans and validates the archive twice. Paging reduces individual response size but repeats headers/endpoints and file scans; it does not demonstrate aggregate token or latency savings. No model experiment was repeated.
