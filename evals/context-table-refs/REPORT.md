# Reuse page tables in archive source-context metadata

The completed v3 caller trace returned 56054 bytes in two pages. Its context metadata repeated caller IDs, source paths and hashes already represented in page-local node/file tables. The renderer now uses source_node and file_number references in each context record, while retaining all other context metadata and numbered source lines. JSON query packets and stored archive records are unchanged. The text header and archive reference explain the table references. This intentionally changes human-readable text metadata; consumers parsing that text must resolve the table references or use JSON. The retained-trace audit recognizes both old and new forms.

The replay loads the frozen v3 archive code and renderer, reproduces both completed model output hashes, and applies only the candidate renderer to the same packets. All node, edge and context metadata reconstruct exactly; every numbered/escaped source display line matches. Same-packet output changes from 28027+28027=56054 to 24785+25066=49851 bytes, a 6203-byte (about 11.1%) reduction. Nothing is dropped to obtain this comparison.

With the new renderer also used for budget decisions, the same 30000-byte/radius-12 query returns 26 then 20 edges (previously 22 then 24), in 29193+20659=49852 bytes. Pagination covers all 46 independently enumerated sites. Both reconstructed packets pass full field/source checks. This is a frozen source/query example, not a size guarantee for every graph, a latency measurement or an actual model token result. Shorter table references may affect model reading; no claim of improved comprehension is made.

Ordinary and candidate engine suites each pass 242 tests, including source-context reconstruction under budget-driven pagination. Root tests pass 53. The diagnostic audit test passes and the completed v3 source-reread result remains exactly equal after supporting both formats. No completed model input or output was changed. No model trial was run for this renderer.

Reproduce with the retained v3 runtime on PYTHONPATH:

```sh
PYTHONPATH=/tmp/columbus-archive-force-bytes-v3-trial/runtime .venv/bin/python \
  evals/context-table-refs/measure.py /tmp/columbus-archive-force-bytes-v3-trial \
  /tmp/context-table-refs.json
```

Fresh wheel and ZIP distribution verification passed; see distribution.txt. Platform CI is pending for the implementation commit.
