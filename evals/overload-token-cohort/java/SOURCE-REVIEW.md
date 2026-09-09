# Prospective Gson overload task: source review

This task and its complete semantic clauses were prepared before model trials. No target code, tests, builds or model trials were executed to establish the oracle. Source files were inspected as data. The catalog, criteria, review, complete source snapshot and runtime/protocol inputs must be frozen before any trial. Historical cohorts and their failures remain unchanged.

## Source identity and verification

- Repository: `google/gson`.
- Commit: `b3f4ca20087f9066de4c340522ff84e0558e1ad1`.
- Complete repository archive: <https://codeload.github.com/google/gson/zip/b3f4ca20087f9066de4c340522ff84e0558e1ad1>.
- Archive SHA-256: `0980ae32fae04e0cdd1c9637b19881e4dbfcda358d77c182e34326daedf49e4e`.
- Archive inventory: 783,863 archive bytes; 313 regular file entries totaling 2,333,811 uncompressed source bytes. Archive bytes and uncompressed source bytes are different quantities.
- `gson/src/main/java/com/google/gson/Gson.java`: SHA-256 `1a33f3eb5ddc01f0a33bbe2b43dc26f8474fc8d5b80876ad9a2f33056224fc94`; 1,288 physical lines.
- `gson/src/main/java/com/google/gson/stream/JsonReader.java`: SHA-256 `8bfbc7efaffcb104f51e1cd222a1d9e9d580b02c816b95257be6d0220bba7086`.
- `gson/src/main/java/com/google/gson/reflect/TypeToken.java`: SHA-256 `f182b1fe6d242196dd846617bf594ce45741103d17bbc3f148219bfeb23db8bd`.
- `gson/src/main/java/com/google/gson/internal/Primitives.java`: SHA-256 `dbee9175d2fb298f3a13589584590e99c638379e8be6f26d2c893259ca9756d7`.
- Apache-2.0 `LICENSE`: SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.

The complete codeload ZIP was independently read in memory, hashed and inventoried. The Gson source was also independently fetched from the pinned raw URL and its hash matched the archive member. All ranges below refer to physical source lines, including blank lines. Browser text extraction can remove blank lines and is not the line-number oracle.

Primary sources: [Gson.java](https://github.com/google/gson/blob/b3f4ca20087f9066de4c340522ff84e0558e1ad1/gson/src/main/java/com/google/gson/Gson.java), [JsonReader.java](https://github.com/google/gson/blob/b3f4ca20087f9066de4c340522ff84e0558e1ad1/gson/src/main/java/com/google/gson/stream/JsonReader.java), [TypeToken.java](https://github.com/google/gson/blob/b3f4ca20087f9066de4c340522ff84e0558e1ad1/gson/src/main/java/com/google/gson/reflect/TypeToken.java), [Primitives.java](https://github.com/google/gson/blob/b3f4ca20087f9066de4c340522ff84e0558e1ad1/gson/src/main/java/com/google/gson/internal/Primitives.java).

## Citation and semantic contract

The case is `java-gson-fromjson-overloads`, with exactly six finding IDs. Every positive behavioral clause in `criteria.json` must be established by correct prose or an actual supporting quote; equivalent wording is accepted. Related findings may supply shared context. Contradictions anywhere fail the affected semantic requirement. Scope exclusions and clauses expressly described as contradiction boundaries do not require unrelated warnings to be recited. Clause IDs are the finding ID and zero-based array index, matching the existing semantic gate; no clauses may be dropped or renumbered after freezing.

Each finding needs one repository-relative citation with a contiguous range of at most 40 physical lines and a contiguous verbatim quote within that range, ignoring indentation as the existing harness does. No ellipses, stitched excerpts or enlarged bounds are needed. A representative quotation does not have to contain every branch supporting the explanation. The descriptions identify the representative mechanism without exposing private source paths, line numbers or literal markers. The answer must synthesize the remaining relevant inspected source in prose; merely citing a broad range does not establish omitted behavior.

The private markers and `call_lines` retain the historical harness representation. Here `call_lines` are reviewed mechanism anchors, not a claim that this is a caller-enumeration task. The base harness checks bounded source grounding; the cohort collector must additionally enforce exactly the six expected IDs once each and the full semantic gate. Declaration search and graph evidence are navigation aids, not the semantic oracle. Neither parser edges nor this source-only review proves arbitrary adapter runtime behavior.

Preparation validation parsed both JSON files, checked matching finding/criterion IDs and all 20 clauses, and compared each of the six quoted blocks literally with its stated ZIP-member range. Each witness contains its marker and reviewed anchor, and all six pass the unchanged `observe_saved_callers.grade` citation check against an in-memory source snapshot. The generated question/finding descriptions contain none of the private paths or literal markers. These checks validate the citation witnesses and catalog contract only; no synthetic explanation was counted as semantic or model-quality evidence.

## overload-routing

Clause IDs: `overload-routing[0]` through `overload-routing[2]`.

Required representative mechanism: the Reader/TypeToken handoff to the core. Private marker: `T object = fromJson(jsonReader, typeOfT);`, line 1004.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1001–1011 (11 physical lines).

```java
  public <T> T fromJson(Reader json, TypeToken<T> typeOfT)
      throws JsonIOException, JsonSyntaxException {
    JsonReader jsonReader = newJsonReader(json);
    T object = fromJson(jsonReader, typeOfT);
    assertFullConsumption(object, jsonReader);
    return object;
  }

  // fromJson(JsonReader, Class) is unfortunately missing and cannot be added now without breaking
  // source compatibility in certain cases, see
  // https://github.com/google/gson/pull/1700#discussion_r973764414
```

Reviewed supporting ranges in Gson.java: 850–881, 909–915, 940–973, 1001–1011, 1045–1049, 1087–1088, 1159–1188 and 1212–1217. TypeToken.java 354–362 supplies both `get` forms. The eleven declaration starts are 850, 879, 909, 940, 971, 1001, 1046, 1087, 1159, 1186 and 1212. Class/Type routes construct TypeToken directly; the Type variants cast their generic return. The absence of a JsonReader/Class declaration does not prevent a Class argument from selecting the Type overload. String and tree wrappers, configured Reader creation and convergence on the core all remain required despite the representative quote covering only one handoff.

## null-shortcuts

Clause IDs: `null-shortcuts[0]` through `null-shortcuts[2]`.

Required representative mechanism: the tree-input shortcut and subsequent delegate. Private marker: `return fromJson(new JsonTreeReader(json), typeOfT);`, line 1216.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1212–1217 (6 physical lines).

```java
  public <T> T fromJson(JsonElement json, TypeToken<T> typeOfT) throws JsonSyntaxException {
    if (json == null) {
      return null;
    }
    return fromJson(new JsonTreeReader(json), typeOfT);
  }
```

Reviewed support: Gson.java 909–915 and 1212–1217; Class/Type routing at 850–881 and 1159–1188; TypeToken.java 79–85 and 354–362. Both Java-null shortcuts precede wrapper construction and adapter lookup. JsonNull.INSTANCE is a non-null tree value, so this identity guard does not determine its converted result. Class/Type target conversion occurs before the guards, motivating the explicit valid-target assumption. Invalid-target exception analysis is outside the task and is not an additional required explanation.

## full-consumption

Clause IDs: `full-consumption[0]` through `full-consumption[3]`.

Required representative mechanism: the completion helper's conditional peek. Private marker: `if (obj != null && reader.peek() != JsonToken.END_DOCUMENT)`, line 1221.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1219–1229 (11 physical lines).

```java
  private static void assertFullConsumption(Object obj, JsonReader reader) {
    try {
      if (obj != null && reader.peek() != JsonToken.END_DOCUMENT) {
        throw new JsonSyntaxException("JSON document was not fully consumed.");
      }
    } catch (MalformedJsonException e) {
      throw new JsonSyntaxException(e);
    } catch (IOException e) {
      throw new JsonIOException(e);
    }
  }
```

Reviewed support: Gson.java 909–915, 1001–1007, 1087–1115, 1130–1135 and 1212–1229. Reader always invokes the helper following a normal core return, but the helper peeks only for a non-null result. A custom adapter returning null therefore also bypasses trailing-input checking. Direct JsonReader and tree routes have no such helper. Describing the direct JsonReader API as reading the next value is valid; claiming that Gson enforces exactly one consumed value for arbitrary custom adapters is not. The helper's malformed-versus-other-I/O mapping differs from the core mapping.

## reader-strictness

Clause IDs: `reader-strictness[0]` through `reader-strictness[2]`.

Required representative mechanism: strictness selection in the core. Private marker: `reader.setStrictness(this.strictness);`, line 1093.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1087–1097 (11 physical lines).

```java
  public <T> T fromJson(JsonReader reader, TypeToken<T> typeOfT)
      throws JsonIOException, JsonSyntaxException {
    boolean isEmpty = true;
    Strictness oldStrictness = reader.getStrictness();

    if (this.strictness != null) {
      reader.setStrictness(this.strictness);
    } else if (reader.getStrictness() == Strictness.LEGACY_STRICT) {
      // For backward compatibility change to LENIENT if reader has default strictness LEGACY_STRICT
      reader.setStrictness(Strictness.LENIENT);
    }
```

Reviewed support: Gson.java 821–825, 1001–1007, 1087–1097 and 1130–1135. New Reader wrappers initially use explicit strictness or LEGACY_STRICT. The core temporarily selects the Gson override or adjusts only LEGACY_STRICT to LENIENT. Existing STRICT is preserved only when Gson has no override. Restoration is in finally, including exceptional exits, and precedes the Reader completion helper. Selection and restoration need not fit in one quote; their full explanation is still required.

## adapter-result-validation

Clause IDs: `adapter-result-validation[0]` through `adapter-result-validation[2]`.

Required representative mechanism: non-null result assignability validation. Private marker: `if (object != null && !expectedTypeWrapped.isInstance(object))`, line 1105.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1099–1115 (17 physical lines).

```java
    try {
      JsonToken unused = reader.peek();
      isEmpty = false;
      TypeAdapter<T> typeAdapter = getAdapter(typeOfT);
      T object = typeAdapter.read(reader);
      Class<?> expectedTypeWrapped = Primitives.wrap(typeOfT.getRawType());
      if (object != null && !expectedTypeWrapped.isInstance(object)) {
        throw new ClassCastException(
            "Type adapter '"
                + typeAdapter
                + "' returned wrong type; requested "
                + typeOfT.getRawType()
                + " but got instance of "
                + object.getClass()
                + "\nVerify that the adapter was registered for the correct type.");
      }
      return object;
```

Reviewed support: Gson.java 1099–1135 and Primitives.java 53–75. Initial peek precedes lookup/read and clearing the empty flag. Primitive target classes are boxed before the non-null `isInstance` check. Assignable subtype results and null results are permitted; generic contents are not inspected by this check. A mismatched result throws ClassCastException, which is absent from the core catch list. No factory enumeration or reflective adapter implementation is needed.

## eof-and-errors

Clause IDs: `eof-and-errors[0]` through `eof-and-errors[3]`.

Required representative mechanism: the core exception-handling block. Private marker: `} catch (EOFException e) {`, line 1116.

Representative citation: `gson/src/main/java/com/google/gson/Gson.java`, lines 1116–1135 (20 physical lines).

```java
    } catch (EOFException e) {
      /*
       * For compatibility with JSON 1.5 and earlier, we return null for empty
       * documents instead of throwing.
       */
      if (isEmpty) {
        return null;
      }
      throw new JsonSyntaxException(e);
    } catch (IllegalStateException e) {
      throw new JsonSyntaxException(e);
    } catch (IOException e) {
      // TODO(inder): Figure out whether it is indeed right to rethrow this as JsonSyntaxException
      throw new JsonSyntaxException(e);
    } catch (AssertionError e) {
      throw new AssertionError(
          "AssertionError (GSON " + GsonBuildConfig.VERSION + "): " + e.getMessage(), e);
    } finally {
      reader.setStrictness(oldStrictness);
    }
```

Reviewed support: Gson.java 1087–1103, 1116–1135 and 1219–1229; JsonReader.java 582–583 and 678–702. The empty flag distinguishes EOFException from the initial peek from later EOF, not every possible exhausted-reader condition. A previously used reader can return END_DOCUMENT from peek; the core does not immediately return null on that token. IllegalStateException and parse I/O are wrapped as JsonSyntaxException with cause. AssertionError adds the Gson build version and preserves the original cause. Unmatched exceptions escape, with strictness restored. Exact version/message transcription and arbitrary adapter outcomes are not required.

## Verification limits

This review establishes source-level behavior and valid representative citation witnesses, not observed model quality or token savings. The complete source snapshot must retain its license and match the archive inventory and hashes when materialized. The six findings contain 20 positive/scope clauses in total, all frozen together. Future acceptance requires every clause and every citation rule in both conditions; no omission, relaxed citation range or post-result rubric adjustment is justified by a smaller answer.
