"""One portable CLI shared by console scripts, python -m, and installed skills."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

from . import __version__
from .index import RepositoryIndex, compact


_WELCOME = '''Columbus — local repository graphs and focused code for agents.

Start inside your repository, or add --repo /path/to/project:
  columbus explore                       # Small repository map
  columbus explore "checkout validation"  # Relevant source, default 2000 estimated tokens
  columbus explore checkout --session checkout-task
  columbus stats checkout-task           # Local response measurements

Reuse a session only when this agent still has its earlier source context.
Use a new name after compaction or for another task. Sessions are optional.
Run columbus --help or columbus explore --help for all options.
'''


def _session_paths(root: Path, name: str) -> tuple[Path, Path]:
    """Resolve one portable session name without creating or following internal links."""
    reserved = {'con', 'prn', 'aux', 'nul', *(f'com{n}' for n in range(1, 10)), *(f'lpt{n}' for n in range(1, 10))}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) or name.lower() in reserved:
        raise ValueError('Session name must be 1–64 ASCII letters, digits, hyphens or underscores, '
                         'start with a letter or digit, and avoid reserved device names')
    directory = root
    for part in ('.columbus', 'sessions', name):
        directory = directory / part
        if directory.is_symlink() or directory.resolve() != directory or (directory.exists() and not directory.is_dir()):
            raise ValueError('Session parent must be a regular directory, never a symlink')
    paths = directory / 'receipt.json', directory / 'queries.jsonl'
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError('Session files must be regular files, never symlinks')
    return paths


def doctor() -> dict:
    from .languages import JVM_DEPENDENCIES
    dependencies = {}
    for name, version in JVM_DEPENDENCIES.items():
        try:
            found = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found = None
        dependencies[name] = {'required': version, 'installed': found, 'matches': found == version}
    conn = sqlite3.connect(':memory:')
    try:
        conn.execute('CREATE VIRTUAL TABLE probe USING fts5(text)')
        fts5 = True
    except sqlite3.Error:
        fts5 = False
    finally:
        conn.close()
    return {'bundle': {'name': 'columbus', 'version': __version__}, 'python': sys.version.split()[0],
            'fts5': fts5, 'dependencies': dependencies,
            'ready': fts5 and all(d['matches'] for d in dependencies.values()),
            'install': 'Install this package or the bundled scripts/requirements.txt in a dedicated environment.'}


def _common(parser, *, subcommand=False):
    default = argparse.SUPPRESS if subcommand else None
    parser.add_argument('--repo', default=default, help='Repository/worktree directory (default current directory)')
    parser.add_argument('--db', default=default, help='Index path; default REPO/.columbus/index-v1.sqlite')
    parser.add_argument('--pretty', action='store_true', default=argparse.SUPPRESS if subcommand else False,
                        help='Indent JSON (byte-budgeted responses always stay compact)')
    parser.add_argument('--telemetry', default=default, metavar='PATH',
                        help='Opt-in local metadata-only query JSONL log (no query or source text)')


def main(argv=None) -> int:
    # Budgets and telemetry describe UTF-8/LF bytes, including redirected pipes.
    # StringIO and embedders without reconfigure keep their original streams.
    for stream, errors in ((sys.stdout, 'strict'), (sys.stderr, 'backslashreplace')):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors=errors, newline='\n')
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stdout.write(_WELCOME)
        return 0
    parser = argparse.ArgumentParser(prog='columbus', description='Local polyglot code graphs and budgeted agent context')
    parser.add_argument('--version', action='version', version=__version__)
    _common(parser)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'init', 'tree', 'hook-install', 'hook-update', 'sync', 'index', 'status', 'search', 'map', 'symbol', 'neighbors', 'impact', 'context', 'explore', 'stats', 'graph', 'export', 'serve', 'telemetry'):
        command = sub.add_parser(name)
        _common(command, subcommand=True)
        if name == 'tree':
            command.add_argument('--label', help='Exact symbol ID, name or qualified label; include ancestors and descendants')
            command.add_argument('--path', help='Repository-relative path glob')
            command.add_argument('--language', help='Detected language filter')
            command.add_argument('--limit', type=int, default=100, help='Maximum nodes, with ancestors emitted first')
            command.add_argument('--include-fallback', action='store_true', help='Also include explicitly labelled heuristic/text nodes')
            command.add_argument('--snapshot', action='store_true')
        if name == 'hook-install':
            command.add_argument('--plan', action='store_true', help='Show the hook destination without installing')
        if name == 'hook-update':
            command.add_argument('--strict', action='store_true', help='Reject parse diagnostics and preserve the prior index')
        if name == 'telemetry':
            command.add_argument('log', help='Local query telemetry JSONL file to summarize')
            command.add_argument('--format', choices=['json', 'text'], default='text')
        if name == 'stats':
            command.add_argument('name', help='Session name under REPO/.columbus/sessions/')
            command.add_argument('--format', choices=['json', 'text'], default='text')
        if name == 'init':
            command.add_argument('--plan', action='store_true', help='Inspect skill install without writing files')
            command.add_argument('--skills-dir', default='.agents/skills', help='Relative skill directory (e.g. .claude/skills)')
        if name == 'index':
            command.add_argument('root', help='Legacy alias for sync --repo ROOT')
        if name in {'sync', 'index', 'status'}:
            command.add_argument('--verify-content', '--check-files', action='store_true', help='Hash source contents to verify freshness')
        if name in {'sync', 'index'}:
            command.add_argument('--source-root', default=None, help='Restrict source directory; also sets Python import root')
        if name in {'search', 'map', 'symbol', 'neighbors', 'impact', 'context', 'explore', 'graph', 'export'}:
            command.add_argument('--snapshot', action='store_true', help='Read saved index without automatic sync')
        if name in {'search', 'map', 'symbol', 'neighbors', 'impact', 'context', 'explore'}:
            command.add_argument('--format', choices=['json', 'text'], default='text' if name == 'explore' else 'json',
                                 help='Compact text for agents or compatible structured JSON')
        if name in {'search', 'context'}:
            command.add_argument('query')
        if name in {'map', 'explore'}:
            command.add_argument('query', nargs='?', default='')
        if name in {'search', 'map', 'context', 'explore', 'graph', 'export'}:
            command.add_argument('--path', help='Repository-relative glob, quoted to prevent shell expansion')
            command.add_argument('--language', help='Detected language name, e.g. python or typescript')
        if name == 'search':
            command.add_argument('--limit', type=int, default=10)
            command.add_argument('--cursor', help='Continue this query/filter on the same indexed revision')
        if name in {'symbol', 'neighbors', 'impact'}:
            command.add_argument('symbol_id')
        if name == 'symbol':
            command.add_argument('--max-lines', type=int, default=80)
        if name in {'neighbors', 'impact', 'graph', 'export'}:
            command.add_argument('--hops', type=int, default=2)
            command.add_argument('--limit', type=int, default=1000 if name in {'graph', 'export'} else 50)
        if name in {'neighbors', 'graph', 'export'}:
            command.add_argument('--direction', choices=['in', 'out', 'both'], default='both')
            command.add_argument('--kinds', nargs='+', choices=['contains', 'calls', 'imports', 'inherits'])
        if name in {'map', 'context', 'explore', 'neighbors', 'impact'}:
            command.add_argument('--budget-bytes', type=int, default=None if name == 'explore' else 6000 if name == 'map' else 12000)
            command.add_argument('--budget-tokens', type=int, help='Estimated tokens = ceil(output UTF-8 bytes / 3), not tokenizer-exact')
        if name in {'context', 'explore'}:
            command.add_argument('--mode', choices=['signatures', 'snippets'], default='snippets')
            command.add_argument('--exclude-id', action='append', default=[], help='Already-seen symbol ID; repeat to avoid resending')
            command.add_argument('--receipt', help='Caller-owned JSON receipt of emitted source spans; use .columbus/session.json')
            command.add_argument('--session', help='Use .columbus/sessions/NAME/{receipt.json,queries.jsonl}; snippets only')
        if name in {'graph', 'export'}:
            command.add_argument('--format', choices=['html', 'graphml', 'mermaid', 'json'], default='html')
            command.add_argument('--output', required=True)
            command.add_argument('--focus', help='Center graph on one exact symbol ID or unambiguous name')
            command.add_argument('--level', choices=['symbol', 'file'], default='symbol')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        if args.command == 'explore':
            if not args.query and (args.mode != 'snippets' or args.receipt is not None or args.exclude_id or args.session is not None):
                raise ValueError('Explore without QUERY returns a map; --mode/--receipt/--exclude-id/--session require QUERY')
            if args.budget_bytes is None and args.budget_tokens is None:
                args.budget_tokens = 2000
            if args.budget_bytes is None:
                args.budget_bytes = 64000
            args.command = 'context' if args.query else 'map'
        session_name = getattr(args, 'session', None)
        if session_name is not None:
            if args.mode != 'snippets':
                raise ValueError('--session requires source snippets; use signatures without a session')
            if args.receipt is not None or args.telemetry is not None:
                raise ValueError('--session selects receipt and telemetry files; do not combine it with --receipt or --telemetry')
        telemetry = None
        if args.telemetry:
            from .telemetry import COMMANDS, TelemetryLog
            if args.command not in COMMANDS:
                raise ValueError('--telemetry is supported by map/search/context/symbol/neighbors/impact')
            if getattr(args, 'receipt', None) and Path(args.receipt).expanduser().absolute() == Path(args.telemetry).expanduser().absolute():
                raise ValueError('Receipt and telemetry must use different files')
            telemetry = TelemetryLog(args.telemetry)
        if args.command == 'telemetry':
            from .telemetry import summarize, summary_text
            summary = summarize(args.log)
            sys.stdout.write(summary_text(summary) if args.format == 'text' else compact(summary) + '\n')
            return 0
        if args.command == 'doctor':
            result = doctor()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['ready'] else 2
        if args.command == 'index':
            args.repo = args.root
        db = Path(args.db).expanduser().resolve() if args.db else None
        if args.repo is None and db and db.is_file():
            root = Path(RepositoryIndex(db).status()['root'])
        else:
            root = Path(args.repo or '.').expanduser().resolve()
        if not root.is_dir():
            raise ValueError('--repo must be an existing local repository directory')
        if args.command in {'hook-install', 'hook-update'}:
            from .hooks import install, update
            result = (install(root, apply=not args.plan) if args.command == 'hook-install'
                      else update(root, db, strict=args.strict))
            print(compact(result))
            return 0
        if args.command == 'stats':
            from .telemetry import summarize, summary_text
            _, log = _session_paths(root, args.name)
            summary = summarize(str(log))
            sys.stdout.write(summary_text(summary) if args.format == 'text' else compact(summary) + '\n')
            return 0
        if session_name is not None:
            from .telemetry import TelemetryLog
            receipt_path, log = _session_paths(root, session_name)
            if db is not None and db in {receipt_path, log}:
                raise ValueError('The index database and session files must use different paths')
            args.receipt, args.telemetry = str(receipt_path), str(log)
            telemetry = TelemetryLog(args.telemetry)
        if args.command == 'init':
            from .bundle import install_bundle
            result = install_bundle(root, apply=not args.plan, skills_dir=args.skills_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
            return 2 if result['status'] in {'error', 'conflict'} else 0
        index = RepositoryIndex(db or root / '.columbus/index-v1.sqlite')
        if args.command == 'tree':
            from .tree import records
            if not args.snapshot:
                index.refresh(root, fast=True)
            elif index.status()['root'] != str(root):
                raise ValueError('Selected index belongs to a different repository')
            for record in records(index, label=args.label, path=args.path, language=args.language,
                                  limit=args.limit, include_fallback=args.include_fallback):
                print(compact(record))
            return 0
        if args.command in {'sync', 'index'}:
            result = index.refresh(root, source_root=args.source_root, fast=not args.verify_content)
        elif args.command == 'status':
            result = index.status(check_files=args.verify_content)
            if result['root'] != str(root):
                raise ValueError('Selected index belongs to a different repository')
        elif args.command == 'serve':
            from .mcp_server import serve
            if index.status()['root'] != str(root):
                raise ValueError('Selected index belongs to a different repository')
            serve(str(index.db))
            return 0
        else:
            if not args.snapshot:
                index.refresh(root, fast=True)
            elif index.status()['root'] != str(root):
                raise ValueError('Selected index belongs to a different repository')
            if args.command == 'search':
                result = index.search(args.query, args.limit, path=args.path, language=args.language, cursor=args.cursor)
            elif args.command == 'symbol':
                result = index.symbol(args.symbol_id, args.max_lines)
            elif args.command in {'neighbors', 'impact'}:
                result = index.neighbors(args.symbol_id, direction='in' if args.command == 'impact' else args.direction,
                                         hops=args.hops, limit=args.limit,
                                         kinds=['calls', 'inherits'] if args.command == 'impact' else args.kinds,
                                         budget_bytes=args.budget_bytes, budget_tokens=args.budget_tokens,
                                         output_format=args.format)
            elif args.command in {'context', 'map'}:
                from .presentation import render
                kwargs = dict(budget_bytes=args.budget_bytes, budget_tokens=args.budget_tokens, path=args.path,
                              language=args.language, output_format=args.format)
                receipt_file = None
                if args.command == 'context' and args.receipt:
                    from .receipts import ReceiptFile
                    receipt_file = ReceiptFile(args.receipt, index.status())
                    kwargs['receipt'] = receipt_file.data
                result = index.context(args.query, mode=args.mode, exclude_ids=args.exclude_id, **kwargs) if args.command == 'context' else index.repo_map(args.query, **kwargs)
                rendered = render(result, args.format)
                sys.stdout.write(rendered)
                sys.stdout.flush()
                if session_name is not None:
                    _session_paths(root, session_name)
                if receipt_file is not None:
                    receipt_file.save(result)
                if telemetry is not None:
                    telemetry.append(args.command, args.format, result, rendered, time.perf_counter() - started)
                return 0
            else:
                from .export import render_graph
                graph = index.graph(args.limit, path=args.path, language=args.language, kinds=args.kinds,
                                    focus=args.focus, hops=args.hops, direction=args.direction, level=args.level)
                output = Path(args.output).expanduser().resolve()
                if output == index.db:
                    raise ValueError('Export destination cannot overwrite the index')
                rendered = compact(graph) if args.format == 'json' else render_graph(graph, args.format)
                output.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation also closes the exists-check/write race.
                with output.open('x', encoding='utf-8') as stream:
                    stream.write(rendered)
                result = {'output': str(output), 'nodes': len(graph['nodes']), 'edges': len(graph['edges']), 'truncated': graph['truncated']}
        if args.command in {'neighbors', 'impact'}:
            from .presentation import render
            rendered = render(result, args.format)
        elif getattr(args, 'format', 'json') == 'text':
            from .presentation import render
            rendered = render(result, 'text', args.command)
        else:
            rendered = (json.dumps(result, ensure_ascii=False, indent=2) if args.pretty else compact(result)) + '\n'
        sys.stdout.write(rendered)
        if telemetry is not None:
            telemetry.append(args.command, args.format, result, rendered, time.perf_counter() - started)
        return 0
    except (ValueError, OSError, RuntimeError, ImportError, SyntaxError, UnicodeError, sqlite3.Error) as exc:
        print(f'columbus: {exc}', file=sys.stderr)
        return 2
