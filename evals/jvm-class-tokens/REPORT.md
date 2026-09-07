# Compiler-backed class-token gap

Before the fix, the implementation at 9ebf60e passed the earlier 31 generic/array-context cases, but the expanded 39-case gate failed two valid array class-token calls in both Java parser environments. This is an unresolved-call coverage gap relevant to issue #4, not a false positive or completed issue fix.

The added cases pair `Class<T>` with an actual value for primitive int/boolean class literals and int[]/String[] class literals. javac 17.0.20.1 accepts the four matching cases and rejects the four mismatched cases. Columbus resolves the matching primitive cases and correctly leaves all mismatches unresolved, but misses both matching array cases. The reports retain all sources, hashes, compiler outputs, references, edges, analyzer hash and parser versions. The gate intentionally exits nonzero while these positive expectations remain unmet.

Two implementation limits explain the misses: reference_type_name only accepts dotted scalar names, so an array class token cannot anchor T; argument_fact also does not extract array_creation_expression types. Fixing only one would be insufficient. A future implementation must preserve primitive array component identity (int[] must not become Integer[] through boxing), dimensionality, reference-type shadowing and conservative assignability. Extend negative compiler cases for those boundaries before asserting new targets.

Reproduce with `PYTHONPATH=skills/columbus/scripts .venv/bin/python evals/jvm-class-tokens/verify.py /opt/homebrew/opt/openjdk@17/bin OUTPUT.json`. For the candidate parser, prepend /tmp/columbus-java-package-runtime to PYTHONPATH. These are local reduced compiler fixtures, not general JVM precision/recall measurements. No model trial, release or issue closure was performed.


## Implemented and locally verified

The resolver now extracts array creation types using AST dimension nodes, retains primitive array components without boxing, and resolves array class-token identities through the existing namespace-aware type lookup. Assignability supports equal arrays, reference-array covariance, and array Object/Cloneable/Serializable supertypes. Primitive arrays do not become boxed arrays or Object[]; nested primitive arrays can correctly be Object[]. Unknown component identities stay unresolved.

The final compiler gate has 51 uniquely named cases and passes with both parser environments. It includes the original 31 checks plus primitive/array tokens, incompatible component types, boxed/primitive separation, dimension mismatch, initializers, reference covariance, array supertypes and source-name shadowing. The original failing 39-case pinned.json/candidate.json remain unchanged; fixed-pinned.json/fixed-candidate.json contain the new passing results. Both environments pass 228 engine tests and root tests pass 53. The candidate platform workflow now runs this expanded compiler gate; platform results for this change are pending.

This fixes the two observed omissions and expands bounded resolution. It is not general Java type checking: custom hierarchy assignability, bounded/explicit generic inference and array-expression validity still require semantic analysis. No whole-project precision/recall, runtime reachability, model token savings or issue closure is claimed.
