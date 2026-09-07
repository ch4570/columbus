"""Generic array result contexts must use resolved type identity."""
import verify_generic_constraints as corpus

gate = corpus.gate
for name, context, declaration, valid in [
    ('array_bootstrap_object', 'Object', '', True),
    ('array_shadowed_object', 'Object', 'class Object {} ', False),
    ('array_qualified_object', 'java.lang.Object', 'class Object {} ', True),
    ('array_cloneable', 'Cloneable', '', True),
    ('array_serializable', 'java.io.Serializable', '', True),
    ('array_shadowed_cloneable', 'Cloneable', 'class Cloneable {} ', False),
]:
    source = declaration + 'class C { static <T> T[] hit(T... values) { return values; } void run() { ' + context + ' result = hit("text"); } }'
    gate.CASES.append((name, valid, valid, {'C.java': source}))

if __name__ == '__main__':
    gate.main()
