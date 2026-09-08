# Getter return-type namespace controls

Before enabling getter-based loop bindings, three cross-package Java cases fix the required type context. a.Source.items returns Collection<Item> in package a; package b separately declares an unrelated Item. In b.C, both an explicitly declared a.Item loop variable and var compile to a/Item.hit. Declaring the variable as the consumer package's Item fails compilation because the elements are a.Item.

Both current parser environments leave all three loop-body calls unresolved. The two valid missing calls are coverage gaps, not successful resolution. javac diagnostics, javap owner references, source files/hashes, analyzer hash and tool versions are retained. Any emitted target must match the manually declared static owner. No code is executed and no runtime-dispatch claim is made.

A getter implementation must carry the return declaration's file/scope type identity into the consumer. Copying the bare return argument Item into the caller scope could choose b.Item, especially for var. This adds a concrete namespace guard to the previously fixed same-file collection cases; it does not redefine their success criteria or claim getter support already exists. The full loop-resolution and actual-token objectives remain open.
