"""Frozen synthetic navigation cases and finite, source-grounded answer checks.

The exact structured facts are the semantic oracle. Prose needs separate review
before comparing trials; this is not a general natural-language truth evaluator
or evidence about a population of real repositories. Building never executes code.
"""
from pathlib import Path, PurePosixPath
import re


ANSWER_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['findings', 'complete', 'limitations'],
    'properties': {
        'findings': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['id', 'path', 'start_line', 'end_line', 'quote', 'explanation', 'facts'],
                'properties': {
                    'id': {'type': 'string'},
                    'path': {'type': 'string', 'description': 'Exact repository-relative POSIX source path.'},
                    'start_line': {'type': 'integer', 'description': 'One-based physical CR/LF source line.'},
                    'end_line': {'type': 'integer', 'description':
                                 'Inclusive physical source line; quote a contiguous range of at most 40 lines '
                                 'that contains all required evidence.'},
                    'quote': {'type': 'string', 'description':
                              'All cited lines verbatim, preserving indentation and Unicode; use LF between '
                              'physical lines and omit the trailing newline. U+0085/U+2028/U+2029 are not line breaks.'},
                    'explanation': {'type': 'string', 'description':
                                    'Explain the cited behavior and state the concrete facts in ordinary prose.'},
                    'facts': {
                        'type': 'array',
                        'description': 'One unique key/value pair for each fact key requested in the finding description. '
                                       'Values are exact source expressions, identifiers, or strings as requested.',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'required': ['key', 'value'],
                            'properties': {'key': {'type': 'string'}, 'value': {'type': 'string'}},
                        },
                    },
                },
            },
        },
        'complete': {'type': 'boolean', 'description':
                     'True only if source evidence resolves all requested concrete runtime behavior; '
                     'reporting every requested finding alone does not establish completeness.'},
        'limitations': {'type': 'array', 'items': {'type': 'string'}, 'description':
                        'Exactly the applicable limitation codes requested by the case; otherwise an empty array.'},
    },
}


def _physical_lines(source: str) -> list[str]:
    """Split only CRLF, CR and LF, preserving Unicode separators inside strings."""
    lines = re.split(r'\r\n|\r|\n', source)
    return lines[:-1] if lines and lines[-1] == '' else lines


def _fixture() -> dict[str, bytes]:
    header = ['# Frozen mixed-newline billing fixture.',
              'NOTICE = "pre\u0085lude\u2028tail\u2029stop"',
              'DECOY = "def retry_delay(attempt): return 999"', '',
              *[f'# setup marker {number:02}' for number in range(1, 17)]]
    billing = [*header, 'def retry_delay(attempt, retryable):',
               '    """Delay in seconds; marker \u0085\u2028\u2029 stays on one physical line."""',
               '    if not retryable or attempt >= 4:', '        return None',
               '    return 2 ** attempt', '',
               'def retry_delay_decoy(attempt):', '    return 999']
    endings = ('\r\n', '\r', '\n')
    files = {'billing/retry.py': ''.join(line + endings[number % 3]
                                       for number, line in enumerate(billing)).encode('utf-8')}
    for number in range(25):
        files[f'commerce/region_{number:02}/checkout.py'] = (
            'def checkout_rule():\n'
            f'    """Return the checkout outcome for region {number:02}."""\n'
            f'    return "checkout-{number:02}-allowed"\n').encode('utf-8')
    files.update({
        'jvm/src/main/java/demo/CheckoutService.java': (
            'package demo;\n\n'
            'public final class CheckoutService {\n'
            '    private final PaymentGateway gateway;\n'
            '    public CheckoutService(PaymentGateway gateway) { this.gateway = gateway; }\n'
            '    public String checkout(String sku) {\n'
            '        return gateway.charge(sku);\n'
            '    }\n'
            '}\n').encode('utf-8'),
        'jvm/src/main/java/demo/PaymentGateway.java': (
            'package demo;\n\n'
            'public interface PaymentGateway {\n'
            '    String charge(String sku);\n'
            '}\n').encode('utf-8'),
        'jvm/src/main/java/demo/GatewayFactory.java': (
            'package demo;\n\n'
            'public final class GatewayFactory {\n'
            '    public static PaymentGateway load(String className) throws Exception {\n'
            '        return (PaymentGateway) Class.forName(className).getDeclaredConstructor().newInstance();\n'
            '    }\n'
            '}\n').encode('utf-8'),
        'automation/retry_router.py': (
            'ROUTES = {}\n\n'
            'def register(name, handler):\n'
            '    ROUTES[name] = handler\n\n'
            'def retry(name, payload):\n'
            '    handler = ROUTES[name]\n'
            '    return handler(payload)\n').encode('utf-8'),
    })
    for number in range(200):
        files[f'catalog/archive_{number // 20:02}/record_{number:03}.py'] = (
            f'"""Archived catalog record {number:03}; unrelated to live checkout rules."""\n\n'
            f'def archived_value_{number:03}():\n'
            f'    return "archive-{number:03}"\n').encode('utf-8')
    return files


def build_fixture(root: Path) -> None:
    """Populate an already-created empty directory; never merge or overwrite."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or next(root.iterdir(), None) is not None:
        raise ValueError('Fixture root must be an existing, empty, non-symlink directory')
    for relative, contents in sorted(_fixture().items()):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(contents)


def _finding(identifier, description, path, start, end, facts):
    lines = _physical_lines(_fixture()[path].decode('utf-8'))
    return {'id': identifier, 'description': description,
            'oracle': {'path': path, 'start_line': start, 'end_line': end,
                       'quote': '\n'.join(lines[start - 1:end]),
                       'facts': facts}}


def cases() -> list[dict]:
    """Return a fresh JSON-serializable catalog; never expose oracle to a model."""
    known = {
        'id': 'known-file-physical-lines',
        'question': 'Explain the retry calculation in billing/retry.py:21-25. Those are physical CR/LF lines; '
                    'earlier U+0085, U+2028 and U+2029 characters inside strings are not new source lines. '
                    'Quote the complete function exactly, including indentation and Unicode. Use an empty '
                    'limitations array. complete means all requested behavior is resolved by source evidence.',
        'findings': [_finding(
            'retry-calculation',
            'Explain retry permission, delay and rejection. Supply fact keys retry_allowed_when '
            '(use the form retryable and attempt < BOUND, replacing BOUND with the source bound), delay_seconds '
            '(the exact returned arithmetic expression), and otherwise (the exact return literal).',
            'billing/retry.py', 21, 25,
            {'retry_allowed_when': 'retryable and attempt < 4', 'delay_seconds': '2 ** attempt', 'otherwise': 'None'})],
        'expected_complete': True, 'required_limitations': [],
    }
    broad = {
        'id': 'broad-candidate-completeness',
        'question': 'In this unfamiliar repository, locate every checkout_rule declaration for regions 00 '
                    'through 24. Return all 25 findings, including candidates beyond the first 20 matches. '
                    'For each, quote its whole three-line function and identify the exact returned string '
                    'without Python quote delimiters. Use an empty limitations array. complete means every '
                    'requested region is source-verified, not that a query returned no more items.',
        'findings': [_finding(
            f'checkout-rule-{number:02}',
            f'Region {number:02}: locate its checkout_rule declaration. Supply fact key return_value '
            '(the exact returned string without quote delimiters) and explain what it returns.',
            f'commerce/region_{number:02}/checkout.py', 1, 3,
            {'return_value': f'checkout-{number:02}-allowed'}) for number in range(25)],
        'expected_complete': True, 'required_limitations': [],
    }
    partial = {
        'id': 'partial-dynamic-dispatch',
        'question': 'Trace the source-supported JVM checkout call, its gateway contract, reflective gateway '
                    'construction and the Python retry registry dispatch. Determine whether all concrete runtime '
                    'callees can be identified from these sources. A missing graph edge does not prove independence. '
                    'complete means all concrete runtime behavior has been resolved from the source. '
                    'For unresolved runtime targets use limitation code '
                    'runtime-targets-unresolved; for the inability to infer independence from absent graph edges '
                    'use missing-edges-not-independence. Report those applicable codes exactly. Quote enough '
                    'contiguous source to show both declarations and the stated dispatch mechanism.',
        'findings': [
            _finding('checkout-dispatch',
                     'Show the gateway field, constructor injection and checkout method. Supply fact keys '
                     'call_expression (the exact call without return/semicolon) and binding '
                     '(use constructor-injected when the constructor supplies the gateway).',
                     'jvm/src/main/java/demo/CheckoutService.java', 4, 8,
                     {'call_expression': 'gateway.charge(sku)', 'binding': 'constructor-injected'}),
            _finding('gateway-contract',
                     'Show the PaymentGateway interface and method declaration. Supply fact keys '
                     'declared_method (the method name only) and concrete_implementation '
                     '(use not specified when the interface provides no concrete implementation).',
                     'jvm/src/main/java/demo/PaymentGateway.java', 3, 5,
                     {'declared_method': 'charge', 'concrete_implementation': 'not specified'}),
            _finding('reflective-construction',
                     'Show the GatewayFactory.load method. Supply fact keys target_selector '
                     '(the parameter naming the runtime class) and construction_expression '
                     '(the exact reflective expression, omitting cast/return/semicolon).',
                     'jvm/src/main/java/demo/GatewayFactory.java', 4, 6,
                     {'target_selector': 'className',
                      'construction_expression': 'Class.forName(className).getDeclaredConstructor().newInstance()'}),
            _finding('python-indirect-route',
                     'Show retry_router.retry. Supply fact keys target_lookup (the expression selecting '
                     'the handler) and call_expression (the expression invoking it, without return).',
                     'automation/retry_router.py', 6, 8,
                     {'target_lookup': 'ROUTES[name]', 'call_expression': 'handler(payload)'}),
        ],
        'expected_complete': False,
        'required_limitations': ['runtime-targets-unresolved', 'missing-edges-not-independence'],
    }
    return [known, broad, partial]


def grade(answer, case, root: Path) -> dict:
    """Require the full finding set, exact source and facts, and honest completeness."""
    reasons = []
    if not isinstance(answer, dict) or set(answer) != {'findings', 'complete', 'limitations'}:
        return {'passed': False, 'reasons': ['answer must contain only findings, complete and limitations'],
                'prose_review_required': True}
    if type(answer['complete']) is not bool or answer['complete'] != case['expected_complete']:
        reasons.append('complete does not match the source-supported completeness of this case')
    limitations = answer['limitations']
    if (not isinstance(limitations, list) or any(not isinstance(value, str) for value in limitations)
            or len(set(limitations)) != len(limitations)
            or set(limitations) != set(case['required_limitations'])):
        reasons.append('limitations must exactly identify the required source limitations')
    supplied = answer['findings']
    if not isinstance(supplied, list):
        return {'passed': False, 'reasons': [*reasons, 'findings must be an array'], 'prose_review_required': True}
    expected = {finding['id']: finding['oracle'] for finding in case['findings']}
    seen = set()
    source_bytes = _fixture()
    root = Path(root).resolve()
    fields = {'id', 'path', 'start_line', 'end_line', 'quote', 'explanation', 'facts'}
    for finding in supplied:
        if not isinstance(finding, dict) or set(finding) != fields or not isinstance(finding.get('id'), str):
            reasons.append('each finding must contain exactly the required fields')
            continue
        identifier = finding['id']
        if identifier not in expected or identifier in seen:
            reasons.append(f'{identifier}: unknown or duplicate finding')
            continue
        seen.add(identifier)
        oracle = expected[identifier]
        if finding['path'] != oracle['path']:
            reasons.append(f'{identifier}: wrong source path')
        start, end = finding['start_line'], finding['end_line']
        valid_range = (type(start) is int and type(end) is int and 1 <= start <= oracle['start_line']
                       and oracle['end_line'] <= end and end - start + 1 <= 40)
        if not valid_range:
            reasons.append(f'{identifier}: wrong physical source range')
        path = root.joinpath(*PurePosixPath(oracle['path']).parts)
        try:
            contents = path.read_bytes() if path.resolve() == path and path.is_file() else None
            if contents != source_bytes[oracle['path']]:
                raise ValueError('cited source changed or is not a regular frozen fixture file')
            lines = _physical_lines(contents.decode('utf-8'))
            if not valid_range or end > len(lines) or finding['quote'] != '\n'.join(lines[start - 1:end]):
                reasons.append(f'{identifier}: quotation is not the exact physical source range')
        except (OSError, ValueError, UnicodeError):
            reasons.append(f'{identifier}: cited source is missing, changed or unsafe')
        facts = finding['facts']
        values = {}
        valid_facts = isinstance(facts, list)
        for fact in facts if isinstance(facts, list) else []:
            if (not isinstance(fact, dict) or set(fact) != {'key', 'value'}
                    or not isinstance(fact['key'], str) or not isinstance(fact['value'], str)
                    or fact['key'] in values):
                valid_facts = False
                continue
            values[fact['key']] = fact['value']
        if not valid_facts or values != oracle['facts']:
            reasons.append(f'{identifier}: structured facts do not match the source semantics')
        explanation = finding['explanation']
        if not isinstance(explanation, str) or not explanation.strip():
            reasons.append(f'{identifier}: explanation must be nonempty; prose semantics require separate review')
    missing = sorted(set(expected) - seen)
    if missing:
        reasons.append('missing findings: ' + ', '.join(missing))
    return {'passed': not reasons, 'reasons': reasons,
            'checked_findings': len(seen), 'required_findings': len(expected), 'prose_review_required': True}
