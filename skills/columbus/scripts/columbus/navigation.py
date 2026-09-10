"""Bounded implementation candidates, separate from resolved calls and runtime DI."""
from __future__ import annotations

import base64
from collections import deque
import hashlib
import json
import re

from .parse_cache import decode_parse_cache
from .retrieval import envelope, fits, limits

TYPE_LIMIT = 200
CANDIDATE_LIMIT = 200
TYPE_KINDS = {'class', 'interface', 'object', 'enum', 'record'}
BUILTINS = {
    'String': 'java.lang.String', 'kotlin.String': 'java.lang.String',
    'Int': 'int', 'kotlin.Int': 'int', 'Long': 'long', 'kotlin.Long': 'long',
    'Boolean': 'boolean', 'kotlin.Boolean': 'boolean', 'Double': 'double',
    'Float': 'float', 'Short': 'short', 'Byte': 'byte', 'Char': 'char',
    'Unit': 'void', 'Any': 'java.lang.Object', 'List': 'java.util.List',
    'Map': 'java.util.Map', 'Set': 'java.util.Set',
}


def _cursor(binding, position):
    return base64.urlsafe_b64encode(json.dumps([binding, position], separators=(',', ':')).encode()).decode().rstrip('=')


def _position(cursor, binding):
    if cursor is None:
        return 0
    try:
        if not isinstance(cursor, str) or len(cursor) > 1024 or not re.fullmatch(r'[A-Za-z0-9_-]+', cursor):
            raise ValueError()
        value = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
        if (not isinstance(value, list) or len(value) != 2 or value[0] != binding
                or type(value[1]) is not int or not 0 <= value[1] <= CANDIDATE_LIMIT):
            raise ValueError()
        return value[1]
    except (ValueError, UnicodeError):
        raise ValueError('Implementation cursor belongs to another revision/scope or is malformed') from None


def _canonical_type(text, symbol, parsed, conn):
    """Resolve explicit parameter type names only; unknown generics stay unknown."""
    generic = set(symbol.get('type_parameters', {}))
    parent = next((s for s in parsed.get('symbols', []) if s['id'] == symbol.get('parent_id')), {})
    generic.update(parent.get('type_parameters', {}))
    unknown = False

    def replace(match):
        nonlocal unknown
        name = match.group()
        if name in generic or name in {'out', 'in', 'extends', 'super'}:
            unknown = True
            return name
        head, dot, tail = name.partition('.')
        suffix = dot + tail
        explicit = {i['qualified'] for i in parsed.get('imports', [])
                    if not i.get('wildcard') and i.get('alias', i.get('name')) == head}
        local = {s['qualname'] for s in parsed.get('symbols', [])
                 if s['name'] == head and s['kind'] in TYPE_KINDS}
        if len(explicit | local) > 1:
            unknown = True
            return name
        if explicit or local:
            return next(iter(explicit | local)) + suffix
        if dot:
            if head[:1].isupper():
                unknown = True
            return BUILTINS.get(name, name)
        qualified = '.'.join(filter(None, [symbol.get('package', ''), name]))
        if conn.execute('select 1 from symbols where qualname=? and kind in (?,?,?,?,?) limit 1',
                        [qualified, *sorted(TYPE_KINDS)]).fetchone():
            return qualified
        if name in BUILTINS or name in {'int', 'long', 'boolean', 'double', 'float', 'short', 'byte', 'char', 'void'}:
            return BUILTINS.get(name, name)
        unknown = True
        return qualified

    normalized = re.sub(r'[A-Za-z_$][\w.$]*', replace, re.sub(r'\s+', '', text).replace('...', '[]'))
    return normalized, unknown


def implementations(index, symbol_id, *, limit=30, hops=6, cursor=None,
                    budget_bytes=6000, budget_tokens=None, output_format='json'):
    """Find source-declared subtype/method candidates, never choose a runtime bean."""
    if type(limit) is not int or not 1 <= limit <= CANDIDATE_LIMIT:
        raise ValueError('Implementation limit must be 1–200')
    if type(hops) is not int or not 1 <= hops <= 8:
        raise ValueError('Implementation hops must be 1–8')
    budget = limits(budget_bytes, budget_tokens)
    with index._read() as conn:
        meta = index._meta(conn)
        target = index._find(conn, symbol_id)
        if target['kind'] not in TYPE_KINDS | {'method'}:
            raise ValueError('Implementation lookup requires a type or method declaration')
        if target['kind'] == 'method':
            if 'declaration_modifiers' not in target:
                raise ValueError('Method modifier metadata is missing; run sync before implementation lookup')
            if set(target['declaration_modifiers']) & {'private', 'static', 'final'}:
                raise ValueError('Target method is not overridable (private, static or final)')
        owner = index._find(conn, target['parent_id']) if target['kind'] == 'method' else target
        if owner['kind'] not in TYPE_KINDS:
            raise ValueError('Method has no indexed declaring type')
        package_limited = (target['kind'] == 'method' and target.get('language') == 'java'
                           and owner['kind'] != 'interface'
                           and not set(target['declaration_modifiers']) & {'public', 'protected'})
        binding = hashlib.sha256(json.dumps([meta['root'], meta['revision'], target['id'], hops]).encode()).hexdigest()
        position = _position(cursor, binding)
        packet = envelope(meta, target['id'], 'implementations', budget, budget_tokens, output_format)
        packet.update(semantic_complete=False, runtime_verified=False, relation='implementation_candidate',
                      scan_truncated=False, next_cursor=None,
                      limitations=['Source subtype/signature candidates; DI, proxies and runtime dispatch are unverified.',
                                   'Generic substitutions, external types and missing inheritance can omit candidates.'])
        cached = {}

        def parsed(symbol):
            path = symbol['path']
            if path not in cached:
                row = conn.execute('select parsed from files where path=?', [path]).fetchone()
                cached[path] = decode_parse_cache(row[0]) if row else {}
            return cached[path]

        expected = [_canonical_type(t, target, parsed(target), conn) for t in target.get('parameter_types', [])]
        pending, visited, found = deque([(owner['id'], [], 0)]), {owner['id']}, {}
        while pending:
            current, inheritance, depth = pending.popleft()
            if depth >= hops:
                if conn.execute("select 1 from edges where target=? and kind='inherits' limit 1", [current]).fetchone():
                    packet['scan_truncated'] = True
                continue
            rows = conn.execute('select e.source,e.path,e.line,s.data from edges e '
                                "join symbols s on s.id=e.source where e.target=? and e.kind='inherits' "
                                'order by e.source,e.path,e.line limit ?', [current, TYPE_LIMIT + 1]).fetchall()
            if len(rows) > TYPE_LIMIT:
                packet['scan_truncated'] = True
            for row in rows[:TYPE_LIMIT]:
                child = json.loads(row['data'])
                if child['id'] in visited:
                    continue
                if len(visited) >= TYPE_LIMIT:
                    packet['scan_truncated'] = True
                    continue
                visited.add(child['id'])
                chain = inheritance + [{'source': child['id'], 'target': current, 'path': row['path'], 'line': row['line']}]
                pending.append((child['id'], chain, depth + 1))
                if child['kind'] == 'interface' or child.get('partial'):
                    continue
                if target['kind'] == 'method':
                    members = conn.execute('select s.data from edges e join symbols s on s.id=e.target '
                                           "where e.source=? and e.kind='contains' and s.kind='method' and s.name=? "
                                           'order by s.id limit ?', [child['id'], target['name'], CANDIDATE_LIMIT + 1]).fetchall()
                    candidates = [json.loads(r[0]) for r in members[:CANDIDATE_LIMIT]]
                    if len(members) > CANDIDATE_LIMIT:
                        packet['scan_truncated'] = True
                else:
                    candidates = [child]
                for candidate in candidates:
                    if package_limited and candidate.get('package') != target.get('package'):
                        continue
                    if (candidate.get('partial') or candidate.get('receiver_type')
                            or (candidate['kind'] == 'method' and
                                ('declaration_modifiers' not in candidate or
                                 set(candidate['declaration_modifiers']) & {'abstract', 'static', 'private'}))):
                        continue
                    signature_match = 'type_inheritance'
                    if target['kind'] == 'method':
                        actual = [_canonical_type(t, candidate, parsed(candidate), conn)
                                  for t in candidate.get('parameter_types', [])]
                        if len(actual) != len(expected):
                            continue
                        if any(a != b and not (au or bu) for (a, au), (b, bu) in zip(actual, expected)):
                            continue
                        signature_match = ('generic_or_type_unresolved' if any(u for _, u in actual + expected)
                                           else 'declared_parameter_types')
                    if len(found) >= CANDIDATE_LIMIT:
                        packet['scan_truncated'] = True
                        continue
                    item = {key: candidate[key] for key in ('id', 'path', 'name', 'qualname', 'kind', 'language',
                            'start_line', 'end_line', 'fidelity', 'parameter_types') if key in candidate}
                    item.update(signature=candidate.get('signature', '')[:240], relation='implementation_candidate',
                                signature_match=signature_match, inheritance=chain, runtime_verified=False)
                    found[item['id']] = item
        ordered = [found[key] for key in sorted(found)]
        if position > len(ordered):
            raise ValueError('Implementation cursor is outside this revision/scope')
        packet.update(visited_types=len(visited), candidate_count=len(ordered), omitted_candidates=len(ordered) - position)
        packet['next_cursor'] = _cursor(binding, position) if position < len(ordered) else None
        packet['truncated'] = bool(packet['next_cursor'] or packet['scan_truncated'])
        if not fits(packet):
            raise ValueError('Budget too small for implementation metadata')
        end = position
        for item in ordered[position:position + limit]:
            packet['items'].append(item)
            packet['omitted_candidates'] = len(ordered) - end - 1
            packet['next_cursor'] = _cursor(binding, end + 1) if end + 1 < len(ordered) else None
            packet['truncated'] = bool(packet['next_cursor'] or packet['scan_truncated'])
            if not fits(packet):
                packet['items'].pop()
                break
            end += 1
        packet['omitted_candidates'] = len(ordered) - end
        packet['next_cursor'] = _cursor(binding, end) if end < len(ordered) else None
        packet['truncated'] = bool(packet['next_cursor'] or packet['scan_truncated'])
        if not fits(packet) or (end == position and position < len(ordered)):
            raise ValueError('Budget too small for the next implementation candidate; increase the budget')
        return packet
