# capfirst caller review

Reviewed every complete lexical owner in oracle.json on Django 4ea267661b260ea0d0c87e9dcb99d70037c6f2fc. These identities and criteria are grader-only. The target returns falsy inputs unchanged, converts other non-strings with str, and uppercases the first character while retaining the remainder. It is decorated with keep_lazy_text. It is distinct from django.template.defaultfilters.capfirst, whose callers in admin/helpers.py are excluded.

| Caller | Required behavior |
| --- | --- |
| ModelAdmin._get_action_description | Capitalize the action name with underscores replaced by spaces only when accessing short_description raises AttributeError. |
| ModelAdmin.history_view | Capitalize and stringify the model's plural verbose name for module_name in history context. Missing objects return a redirect and denied permissions raise before this. Extra context can override the resulting value. |
| AdminSite._build_app_dict | Capitalize each included model's plural verbose name for its displayed name, after module permission and any model permission checks; the optional app label restricts candidates. |
| date_hierarchy | With a configured hierarchy, capitalize the year-month back title and month-day choice at day detail (two sites); month-day titles for day choices at month detail; year-month titles for month choices at year detail. The all-years branch does not capitalize titles. Initial date range inference can select a narrower level. |
| get_deleted_objects.format_callback | The nested callback capitalizes the model verbose name for the plain representation unconditionally, then again for the linked representation when registered and URL reversal succeeds. An unavailable URL or unregistered model returns the plain value. Missing delete permission records a requirement but does not itself bypass the linked branch. Attribute these calls to the nested function, not its enclosing owner. |
| AuthenticationForm.__init__ | Supply a capitalized username-field verbose name only if the existing username label is None. |
| Command.handle | In interactive mode, after the TTY check, capitalize the username field's verbose name in the explicitly empty username error. Calls through _validate_username elsewhere are transitive. |
| Command._get_input_message | Capitalize the field verbose name at the start of an input prompt; optional default and relationship information are appended. |
| Command._validate_username | Capitalize the supplied verbose field name in the falsy-username error, after the uniqueness lookup and its possible already-taken early return. |
| Model.date_error_message | Capitalize model verbose name, constrained field verbose name, and date field verbose name for three validation-error parameters. |
| Model.unique_error_message | Always capitalize the model name; capitalize the single field label in the one-field branch, or each field label for the composite uniqueness message in the other branch. Three syntactic sites. |
| Field.formfield | Compute a capitalized verbose name as the default form label. Later kwargs can override that label without bypassing this computation. Choices handling does not bypass the call. |
| BaseInlineFormSet.add_fields | In the branch where the foreign key differs from the primary-key field, compute a capitalized foreign-key verbose name as getattr's default label. Python eagerly evaluates this default even when an existing field label is present; only selection of the default depends on missing label. The primary-key branch bypasses the call. |
| SeleniumTestCaseBase.__new__ | Capitalize each remaining browser name as a prefix for generated subclass names. Browser-specific classes or classes without test methods return early; the first browser reuses the original class; no configured browsers yields a skipped class. This is included library code under django/test/. |

A passing answer must identify exactly 14 lexical callers and explain all 22 syntactic sites with the relevant conditions above. Each finding needs a valid bounded contiguous source quote containing a direct call. Equivalent semantic explanations are acceptable; exhaustive unrelated function behavior is unnecessary. Do not accept same-name filter callers, enclosing-function double counting, or claims that the static inventory proves runtime reachability. In particular, evaluate eager computation separately from whether its result is used.

The XZ and gzip receipts show exact archive/SQLite edge parity and independent AST inventory parity across 883 source files. These checks establish this bounded source-level inventory, not general graph completeness or token savings. No model trial has started.
