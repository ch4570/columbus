# Issue #8: remaining access/static-context contradictions

Observed at 6c4c968 with javac 17.0.20.1; analyzer/source hashes and exact compiler diagnostics are retained in the JSON captures. No application was run; each generated fixture was compiled independently with annotation processing disabled.

[Value-receiver and lexical-call cases](value-receivers.json) expose two false edges: a foreign class calling a private instance method through a typed parameter, and an unqualified instance method call from a static method. Javac rejects both; Columbus emits the target with `confidence=heuristic` and no parse recovery. Four positive controls compile and retain their call targets: public foreign receiver, private nestmate receiver, instance call from an instance method, and static call from a static method.

The declaration extractor does not retain Java access/static modifiers and the resolver does not check them. The expected correction must reject those demonstrably invalid edges while retaining the four controls, including legal private nestmate access. This is an observed remaining failure, not a passing acceptance gate or completed issue fix.

An [earlier type-qualified probe](type-receivers.json) is retained too: `T.hit()` stays unresolved even in valid static/nestmate cases because current value binding handling treats the class declaration as an untyped receiver binding. That coverage limitation did not reproduce the intended false edge; moving the receiver to an explicitly typed value exposed the access defect. Do not interpret missing type-qualified edges as evidence that access/static semantics are implemented.
