# Collection loop declaration controls

Ten compiler-backed cases are fixed before enabling collection-loop body resolution. Seven valid hit calls remain unresolved in both current grammar environments; no incorrect call target is emitted in the three negative programs. The cases include fully qualified List<Item>, a Collection<Item> getter and receiver getter, var, extends/super wildcards, raw List, an unrelated source class named List, a custom Iterable<Item> implementation, and subtype elements.

javac and javap support the manually declared static owners for valid cases. Source text, hashes, diagnostics, bytecode, analyzer hash and parser/compiler versions are retained. The gate rejects any emitted target that differs from the declared owner; unresolved valid calls remain explicit gaps, not successful resolution. No repository or fixture code is executed.

The negative cases rule out recognizing iterable element types by basename alone or stripping all wildcard/generic syntax. Collection getter support must use the actually resolved declaration and its return type; custom iterable inheritance and subtype element conversion need their own evidence. A java.util.List<Item> parameter and a same-named non-iterable class must not share a resolver path merely because their final type names match.

This is a fixed diagnostic corpus for issue #4, not a population precision estimate, a runtime dispatch oracle, or proof of model token savings. Runtime behavior is unchanged in this step. The existing Spring protocolResolver loop and all seven valid calls here remain open work.
