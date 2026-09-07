# Conditional escape caller review

Reviewed every complete lexical owner recorded in oracle.json at Django 4ea267661b260ea0d0c87e9dcb99d70037c6f2fc. Expected caller identities and these notes are grader-only. The target coerces Promise values, uses an object's __html__ result when available, and otherwise calls escape. Conditional escaping does not mean unconditional re-escaping or general validation of HTML safety.

| Caller | Required behavior |
| --- | --- |
| AdminField.label_tag | Escape the field label before passing it as marked-safe label contents; checkbox/required/inline choices affect label styling or suffix, not whether this conversion occurs. |
| AdminReadonlyField.contents | Escape the computed readonly representation or empty display at the final return; the read_only widget.render early return bypasses it. |
| Template.render (dummy backend) | Escape each value of a supplied context dictionary; None becomes an empty dictionary. Request CSRF values are inserted afterward. |
| render_value_in_context | Escape the localized/time-adjusted value only when context.autoescape is enabled; coerce a non-string first. Disabled autoescape returns str directly. |
| escape_filter | Apply conditional escaping to the filter value, preserving the target's __html__ convention. |
| escapeseq | Apply conditional escaping to each element and return a list. |
| join | When autoescape is enabled, escape both separator and each sequence element (two syntactic calls on line 611). Otherwise join directly; TypeError returns the original value. |
| URLNode.render | Escape the reversed URL only in the output branch with autoescape; assignment through asvar stores the URL and returns an empty string before escaping. |
| SimpleNode.render | Escape tag-function output only with autoescape and no target-variable assignment; assignment returns early. |
| StaticNode.render | Escape the URL with autoescape before either returning it or assigning it to varname. Unlike the previous two render methods, assignment does not bypass escaping. |
| format_html | Directly escape keyword argument values; positional values are passed through map(conditional_escape, args), a higher-order use outside the syntactic direct-call count. The formatting result is marked safe. |
| format_html_join | Directly escape the separator before joining fragments; fragment arguments are handled through format_html, not additional direct calls here. |

A passing answer must contain the exact 12 lexical owners, distinguish their inputs and relevant control flow, cover both join sites, and correctly distinguish direct keyword conversion from higher-order positional conversion in format_html. Each finding must cite an actual direct-call line in a bounded contiguous source quote. No extra transitive caller findings or unsupported runtime-completeness claims. Review equivalent explanations on their meaning rather than exact wording. This corpus has not yet been run as a model trial.
