# Independent caller review

Reviewed the complete lexical owner ranges recorded in oracle.json against source revision 4ea267661b260ea0d0c87e9dcb99d70037c6f2fc. These notes are private evaluation expectations, not model prompt content. The definition is syntactic direct calls in production Python files, not indirect or runtime callers. The target converts an IRI portion to URI-compatible escaped form and preserves None; it does not validate whether a redirect is safe.

| Caller | Conversion purpose and relevant condition |
| --- | --- |
| FlatPage.get_absolute_url | Fallback after reverse attempts fail: convert manually joined script prefix and flatpage URL. |
| add_domain | Convert the constructed protocol/domain/path URL only in the relative-URL branch; the network-path branch adds a protocol without this call. |
| HttpRequest._get_full_path | Defensively encode a nonempty QUERY_STRING; path escaping is a separate operation. |
| HttpRequest.build_absolute_uri | Convert the resulting location after absolute or request-relative URL construction. |
| HttpResponseRedirectBase.__init__ | Encode redirect_to for the Location header; subsequent length/scheme checks are separate. |
| iriencode | Template filter that converts its IRI value for use in a URL. |
| PrefixNode.handle_simple | Convert the named settings prefix when settings import succeeds; otherwise return an empty prefix. |
| Stylesheet.url | Convert the stored stylesheet URL when accessing the property; surrounding source explains delayed lazy evaluation. |
| Stylesheet.__str__ | Convert the stylesheet href before serializing the attribute dictionary. |
| SyndicationFeed.__init__ | Convert feed link, author_link and feed_url when constructing feed metadata. |
| SyndicationFeed.add_item | Convert item link and author_link when appending item metadata. |
| Enclosure.__init__ | Convert the enclosure URL stored in self.url. |

A future model answer must identify all 12 owners, cover all 15 sites (including the three feed constructor fields and two item fields), avoid test callers and false extra owners, and substantiate these roles with exact source ranges and contiguous quotes. Accept equivalent wording; do not require this prose verbatim. Generic "URL encoding" alone does not explain each usage. No model run has started.

# Graph and storage observations

verify_graph.py checks the full 883-file production manifest against current source and indexed hashes, then compares sorted (path, owner, line) lists with the independent AST oracle, preserving multiplicity. There are no missing or extra production calls. The compressed archive returns all 21 stored incoming call edges (including tests) in three 6,000-byte-budget pages with offsets 0, 9 and 19, exactly matching SQLite evidence. The consumer query must still filter production paths for this task.

The archive is 8,785,093 bytes versus 147,763,200 bytes for the local SQLite file (about 5.95% of its size). These artifacts have different capabilities: the archive omits source bodies and the full-text search store. This is storage evidence, not token-savings evidence or runtime completeness. The temporary verification archive is deleted after checking; its checksum and measurements are retained in graph-verified.json. Production source and SQLite remain available locally for the forthcoming frozen evaluation.
