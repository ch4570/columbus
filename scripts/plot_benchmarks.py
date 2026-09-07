#!/usr/bin/env python3
"""Render benchmark JSON as publication figures; matplotlib is a developer tool only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
VERSION_DIR = ROOT / 'docs/benchmarks/1.0.0'
HISTORY = ROOT / 'evals/exploration/results/2026-09-07/controlled.json'
COLORS = {'paper': '#FBF7EE', 'navy': '#183342', 'teal': '#16776F',
          'coral': '#B84935', 'muted': '#566973', 'grid': '#DCDDD5'}


def number(value, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} must be a finite nonnegative number')
    return value


def unique(rows: list[dict], **match) -> dict:
    found = [row for row in rows if all(row.get(key) == value for key, value in match.items())]
    if len(found) != 1:
        raise ValueError(f'Expected one measurement for {match}, got {len(found)}')
    return found[0]


def delivery_series(data: dict) -> dict:
    rows = data['rows']
    ordered_ids = data['same_map_ids']
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise ValueError('The complete map must contain unique ordered IDs')
    map_rows = [unique(rows, comparison='same_map', format=fmt) for fmt in ('json', 'text')]
    for row in map_rows:
        if row['truncated'] or row['returned_items'] != len(ordered_ids):
            raise ValueError('Same-map comparison changed or truncated the item set')
    repeated = [[unique(rows, comparison='repeated_context', receipt=receipt, call=call)
                 for call in range(1, 4)] for receipt in (False, True)]
    for row in map_rows + repeated[0] + repeated[1]:
        number(row['output_bytes'], 'output_bytes')
        number(row['source_bytes'], 'source_bytes')
        if row['source_bytes'] > row['output_bytes']:
            raise ValueError('Source bytes cannot exceed the complete output')
    map_bytes = [row['output_bytes'] for row in map_rows]
    output_totals = [sum(row['output_bytes'] for row in condition) for condition in repeated]
    if not map_bytes[0] or not output_totals[0]:
        raise ValueError('Reduction comparisons need nonzero baselines')
    return {'engine_version': data['engine_version'], 'map_items': len(ordered_ids),
            'map_bytes': map_bytes, 'map_reduction_pct': (1 - map_bytes[1] / map_bytes[0]) * 100,
            'output_totals': output_totals,
            'output_reduction_pct': (1 - output_totals[1] / output_totals[0]) * 100,
            'source_by_call': [[row['source_bytes'] for row in condition] for condition in repeated],
            'output_by_call': [[row['output_bytes'] for row in condition] for condition in repeated]}


def historical_series(data: dict) -> list[dict]:
    result = []
    for case in data['manifest']['case_ids']:
        trials = [unique(data['trials'], case=case, condition=condition, repeat=1)
                  for condition in ('baseline', 'repoatlas')]
        pair = unique(data['pairs'], case=case, repeat=1)
        passed = [trial['quality']['passed'] for trial in trials]
        if any(not isinstance(value, bool) for value in passed):
            raise ValueError('Citation status must be explicit')
        if not pair['settings_match'] or not pair['preflight_valid'] or pair['quality_gated'] != all(passed):
            raise ValueError('Pair comparability does not match the trial evidence')
        for trial in trials:
            if trial['timed_out'] or trial['return_code'] != 0:
                raise ValueError('Incomplete model trial must not be presented as a completed comparison')
        inputs = [number(trial['usage']['input_tokens'], 'input_tokens') for trial in trials]
        for trial, value, condition in zip(trials, inputs, ('baseline', 'repoatlas')):
            cached = number(trial['usage']['cached_input_tokens'], 'cached_input_tokens')
            if cached > value or pair['measures']['input_tokens'][condition] != value:
                raise ValueError('Token summary does not agree with the recorded trial')
        if not inputs[0]:
            raise ValueError('Input token comparison needs a nonzero baseline')
        result.append({'case': case, 'input_tokens': inputs, 'citation_passed': passed,
                       'both_citations_passed': all(passed),
                       'change_pct': (inputs[1] / inputs[0] - 1) * 100})
    return result


def incremental_series(data: dict) -> dict:
    result = {}
    for phase in ('cold', 'warm', 'one_file_changed'):
        rows = [row for row in data['runs'] if row['phase'] == phase]
        if len(rows) != data['repeats'] or {r['repeat'] for r in rows} != set(range(1, data['repeats'] + 1)):
            raise ValueError(f'Incomplete or duplicated incremental phase: {phase}')
        seconds = [number(row['elapsed_seconds'], 'elapsed_seconds') for row in rows]
        parsed = [number(row['parsed_files'], 'parsed_files') for row in rows]
        result[phase] = {'median_seconds': statistics.median(seconds),
                         'min_seconds': min(seconds), 'max_seconds': max(seconds),
                         'parsed_files': parsed[0]}
        if len(set(parsed)) != 1:
            raise ValueError('Parsing counts differ across repeats; inspect the measurements')
    return result


def initialize_plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'text.color': COLORS['navy'], 'axes.labelcolor': COLORS['muted'],
                         'xtick.color': COLORS['muted'], 'ytick.color': COLORS['navy'],
                         'figure.facecolor': COLORS['paper'], 'axes.facecolor': COLORS['paper'],
                         'savefig.facecolor': COLORS['paper'], 'svg.fonttype': 'path',
                         'svg.hashsalt': 'columbus-benchmarks-v1', 'axes.titleweight': 'bold'})
    return matplotlib, plt


def heading(fig, eyebrow: str, title: str, subtitle: str):
    fig.text(.065, .956, eyebrow, fontsize=10, weight='bold', color=COLORS['teal'])
    fig.text(.065, .895, title, fontsize=24, weight='bold')
    fig.text(.065, .85, subtitle, fontsize=11, color=COLORS['muted'])


def axis_style(ax, horizontal=True):
    from matplotlib.ticker import StrMethodFormatter
    ax.set_axisbelow(True)
    ax.grid(axis='x' if horizontal else 'y', color=COLORS['grid'], linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0, pad=8)
    if horizontal:
        ax.set_xlim(left=0)
        ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
    else:
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))


def horizontal_comparison(ax, values, labels, title, change):
    ax.barh([1, 0], values, color=[COLORS['navy'], COLORS['teal']], height=.4)
    ax.set_yticks([1, 0], labels)
    ax.set_xlim(0, max(values) * 1.27)
    ax.set_ylim(-.65, 1.65)
    axis_style(ax)
    ax.set_xlabel('Complete output · UTF-8 bytes', labelpad=12, fontsize=10)
    ax.set_title(title, loc='left', pad=33, fontsize=13)
    ax.text(0, 1.13, f'{change:.1f}% smaller', transform=ax.transAxes,
            color=COLORS['teal'], fontsize=11, weight='bold')
    for y, value in zip((1, 0), values):
        ax.text(value + max(values) * .035, y, f'{value:,.0f}', va='center', weight='bold', fontsize=11)


def draw_delivery(plt, data):
    series = delivery_series(data)
    fig = plt.figure(figsize=(12, 9.6))
    heading(fig, f'COLUMBUS {series["engine_version"]}  /  CLI DELIVERY',
            'Less repeated text. Measured in bytes.',
            'Captured CLI output on the bundled polyglot fixture. These values are not model tokens.')
    left = fig.add_axes([.115, .575, .33, .16])
    right = fig.add_axes([.63, .575, .295, .16])
    horizontal_comparison(left, series['map_bytes'], ['JSON', 'Text'],
                          f'The same {series["map_items"]} map symbols', series['map_reduction_pct'])
    horizontal_comparison(right, series['output_totals'], ['No receipt', 'Receipt'],
                          'Three checkout queries', series['output_reduction_pct'])
    ax = fig.add_axes([.115, .19, .81, .22])
    width = .27
    maximum = max(max(row) for row in series['source_by_call'])
    for offset, values, label, color in zip((-.15, .15), series['source_by_call'],
                                           ('No receipt', 'Receipt'), (COLORS['navy'], COLORS['teal'])):
        positions = [i + offset for i in range(3)]
        ax.bar(positions, values, width=width, color=color, label=label)
        for x, value in zip(positions, values):
            ax.text(x, value + maximum * .04, f'{value:,.0f}', ha='center', va='bottom', weight='bold')
    ax.set_xticks(range(3), ['Call 1', 'Call 2', 'Call 3'])
    ax.set_ylim(0, maximum * 1.23)
    ax.set_ylabel('Returned source · UTF-8 bytes', labelpad=12, fontsize=10)
    ax.set_title('Receipts remember source already delivered', loc='left', pad=26, fontsize=13)
    ax.legend(frameon=False, ncol=2, loc='lower right', bbox_to_anchor=(1, 1.065), fontsize=10)
    axis_style(ax, horizontal=False)
    fig.text(.065, .1, f'Call 3 with a receipt: {series["source_by_call"][1][2]:,} source bytes; '
             f'{series["output_by_call"][1][2]:,} response bytes remain for metadata.', fontsize=10)
    fig.text(.065, .071, 'Map IDs and order match; text omits JSON metadata. Later receipt calls may expose additional source.',
             fontsize=9, color=COLORS['muted'])
    fig.text(.065, .042, 'Source: docs/benchmarks/1.0.0/delivery.json · same query three times · no billing or task-quality claim',
             fontsize=9, color=COLORS['muted'])
    description = ('Columbus CLI byte measurements. ' + json.dumps(series, sort_keys=True) +
                   '. Same map IDs and order, not identical metadata. No model-token or billing claim.')
    return fig, series, description


def draw_historical(plt, data):
    series = historical_series(data)
    fig = plt.figure(figsize=(12, 8.6))
    heading(fig, 'HISTORICAL OBSERVATION  /  REPOATLAS 0.4.0',
            'Smaller output does not guarantee fewer tokens.',
            'Actual Codex cumulative input tokens. This is historical evidence, not a Columbus 1.0.0 model A/B test.')
    ax = fig.add_axes([.245, .27, .655, .48])
    maximum = max(max(row['input_tokens']) for row in series)
    names = {'export-safety': 'Export safety', 'configuration-invalidation': 'Config invalidation',
             'managed-installation': 'Managed installation'}
    for position, row in enumerate(series):
        for offset, value, passed, color, label in zip((.17, -.17), row['input_tokens'], row['citation_passed'],
                                                       (COLORS['navy'], COLORS['teal']),
                                                       ('Baseline · rg + bounded reads', 'RepoAtlas 0.4.0')):
            ax.barh(position + offset, value, height=.25, color=color,
                    hatch='///' if not passed else None, edgecolor=COLORS['paper'],
                    label=label if position == 0 else None)
            status = 'PASS' if passed else 'FAIL*'
            ax.text(value + maximum * .025, position + offset, f'{value:,}  {status}',
                    va='center', fontsize=10, weight='bold', color=COLORS['navy'] if passed else COLORS['coral'])
        comparison = f'{row["change_pct"]:+.1f}% input'
        if not row['both_citations_passed']:
            comparison += ' · not quality-matched'
        ax.text(0, position - .41, comparison, fontsize=9,
                color=COLORS['coral'] if row['change_pct'] > 0 else COLORS['muted'])
    ax.set_yticks(range(len(series)), [names.get(row['case'], row['case']) for row in series])
    ax.set_xlim(0, maximum * 1.36)
    ax.set_ylim(-.62, len(series) - .48)
    ax.invert_yaxis()
    axis_style(ax)
    ax.set_xlabel('Cumulative input tokens · includes cached input', fontsize=10, labelpad=12)
    ax.legend(loc='lower left', bbox_to_anchor=(-.275, 1.025), frameon=False, ncol=2, fontsize=10)
    both_pass = [row for row in series if row['both_citations_passed']]
    if len(both_pass) == 1:
        fig.text(.065, .181, f'The only pair with both citation checks passing used '
                 f'{both_pass[0]["change_pct"]:+.1f}% input tokens with RepoAtlas.',
                 fontsize=12, weight='bold', color=COLORS['coral'])
    fig.text(.065, .135, '* FAIL marks non-verbatim source quotes containing ellipses; it does not establish semantic failure.',
             fontsize=9, color=COLORS['muted'])
    env = data['environment']
    fig.text(.065, .103, f'{env["model_requested"]} / {env["reasoning_effort_requested"]} requested · '
             f'Codex {env["codex_cli"]} · one run per case/condition · prebuilt index', fontsize=9, color=COLORS['muted'])
    fig.text(.065, .071, 'Startup/context overhead is included. Cached input is a subset, not an extra amount. No billing claim.',
             fontsize=9, color=COLORS['muted'])
    fig.text(.065, .039, 'Source: evals/exploration/results/2026-09-07/controlled.json · all six completed trials retained',
             fontsize=9, color=COLORS['muted'])
    description = ('Historical RepoAtlas 0.4.0, not a new Columbus 1.0.0 experiment. ' +
                   json.dumps(series, sort_keys=True) + '. FAIL denotes citation-contract failure, not semantic failure. '
                   'One run per condition/case; cached input included in total input; no billing savings claim.')
    return fig, series, description


def draw_incremental(plt, data):
    series = incremental_series(data)
    fig = plt.figure(figsize=(12, 6.6))
    heading(fig, f'COLUMBUS {data["engine_version"]}  /  INCREMENTAL INDEX',
            'Revisit the repository. Parse only the changes.',
            f'Synthetic fixture: {data["fixture"]["files"]:,} Python files. '
            f'{data["repeats"]} repeats per phase on {data["environment"]["system"]} '
            f'{data["environment"]["machine"]}.')
    phases = list(series)
    labels = ['Empty index', 'Unchanged', 'One file edited']
    values = [series[phase]['median_seconds'] for phase in phases]
    errors = [[series[phase]['median_seconds'] - series[phase]['min_seconds'] for phase in phases],
              [series[phase]['max_seconds'] - series[phase]['median_seconds'] for phase in phases]]
    ax = fig.add_axes([.1, .3, .38, .43])
    ax.bar(range(3), values, color=[COLORS['navy'], COLORS['teal'], COLORS['coral']], width=.53,
           yerr=errors, capsize=4, error_kw={'ecolor': COLORS['navy'], 'linewidth': 1})
    ax.set_xticks(range(3), labels, fontsize=9)
    ax.set_ylim(0, max(series[phase]['max_seconds'] for phase in phases) * 1.25)
    for position, value in enumerate(values):
        ax.text(position, series[phases[position]]['max_seconds'] + max(values) * .035,
                f'{value:.3f}s', ha='center', fontsize=11, weight='bold')
    ax.set_ylabel('Median elapsed seconds', fontsize=10, labelpad=12)
    axis_style(ax, horizontal=False)
    from matplotlib.ticker import StrMethodFormatter
    ax.yaxis.set_major_formatter(StrMethodFormatter('{x:g}'))
    ax = fig.add_axes([.605, .3, .32, .43])
    counts = [series[phase]['parsed_files'] for phase in phases]
    ax.bar(range(3), counts, color=[COLORS['navy'], COLORS['teal'], COLORS['coral']], width=.53)
    ax.set_xticks(range(3), labels, fontsize=9)
    ax.set_ylim(0, max(counts) * 1.25)
    for position, value in enumerate(counts):
        ax.text(position, value + max(counts) * .035, f'{value:,}', ha='center', fontsize=11, weight='bold')
    ax.set_ylabel('Files parsed per refresh', fontsize=10, labelpad=12)
    axis_style(ax, horizontal=False)
    fig.text(.065, .175, 'Whiskers show the minimum and maximum of three runs; they are not confidence intervals.', fontsize=10)
    fig.text(.065, .127, 'Each repeat starts with an empty SQLite index. OS caches were not cleared; timings are machine-specific.',
             fontsize=9, color=COLORS['muted'])
    fig.text(.065, .084, 'An unchanged scan still checks file metadata. No claim about agent reasoning quality or model cost.',
             fontsize=9, color=COLORS['muted'])
    fig.text(.065, .041, 'Source: docs/benchmarks/1.0.0/incremental.json · deterministic fixture and engine hashes included',
             fontsize=9, color=COLORS['muted'])
    return fig, series, 'Measured synthetic incremental indexing. ' + json.dumps(series, sort_keys=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_figure(fig, target: Path, description: str, title: str) -> list[Path]:
    target.parent.mkdir(parents=True, exist_ok=True)
    svg, png = target.with_suffix('.svg'), target.with_suffix('.png')
    fig.savefig(svg, metadata={'Date': None, 'Creator': 'Columbus benchmark publisher',
                              'Title': title, 'Description': description})
    # Paths embed glyphs for portable rendering; title/desc retain accessible chart content.
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    tree = ET.parse(svg)
    root = tree.getroot()
    root.set('role', 'img')
    root.set('aria-labelledby', 'chart-title chart-description')
    for tag, identifier, content in (('title', 'chart-title', title), ('desc', 'chart-description', description)):
        element = ET.Element('{http://www.w3.org/2000/svg}' + tag, {'id': identifier})
        element.text = content
        root.insert(0 if tag == 'title' else 1, element)
    tree.write(svg, encoding='utf-8', xml_declaration=True)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines()) + '\n',
                   encoding='utf-8')
    fig.savefig(png, dpi=160, metadata={'Software': 'Columbus benchmark publisher', 'Description': description})
    return [svg, png]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delivery', type=Path, default=VERSION_DIR / 'delivery.json')
    parser.add_argument('--historical', type=Path, default=HISTORY)
    parser.add_argument('--incremental', type=Path, default=VERSION_DIR / 'incremental.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs/assets')
    parser.add_argument('--manifest', type=Path, default=VERSION_DIR / 'charts.json')
    parser.add_argument('--only', choices=('delivery', 'agent-tokens', 'incremental'))
    args = parser.parse_args()
    matplotlib, plt = initialize_plotting()
    charts = []
    for name, source, draw in (('delivery', args.delivery, draw_delivery),
                               ('agent-tokens', args.historical, draw_historical),
                               ('incremental', args.incremental, draw_incremental)):
        if args.only and args.only != name:
            continue
        data = json.loads(source.read_text(encoding='utf-8'))
        fig, series, description = draw(plt, data)
        outputs = save_figure(fig, args.output_dir / f'benchmark-{name}', description, f'Columbus benchmark: {name}')
        plt.close(fig)
        relative = lambda path: path.resolve().relative_to(ROOT).as_posix() if path.resolve().is_relative_to(ROOT) else path.name
        charts.append({'name': name, 'source': relative(source), 'source_sha256': sha256(source),
                       'series': series, 'outputs': {relative(path): sha256(path) for path in outputs}})
    manifest = {'schema': 'columbus.benchmark-charts/v1', 'renderer': 'matplotlib',
                'renderer_version': matplotlib.__version__, 'python_version': platform.python_version(),
                'script': 'scripts/plot_benchmarks.py', 'script_sha256': sha256(Path(__file__)),
                'theme': COLORS, 'svg_fonts': 'embedded paths; accessible title and description',
                'png_dpi': 160, 'charts': charts,
                'note': 'Derived figures use measured JSON. Historical model trials remain attributed to RepoAtlas 0.4.0.'}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(args.manifest), 'charts': [row['name'] for row in charts]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
