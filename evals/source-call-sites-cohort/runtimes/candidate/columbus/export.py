"""Dependency-free graph exports, including a safe, offline graph explorer.

The HTML contains symbol metadata and relationship evidence, never source file
contents. All repository-derived strings enter the DOM through ``textContent``.
"""

from __future__ import annotations

import json
import math
from typing import Any
from xml.etree import ElementTree as ET


HTML_NODE_LIMIT = 5_000
HTML_EDGE_LIMIT = 20_000
MERMAID_NODE_LIMIT = 80
MERMAID_EDGE_LIMIT = 160
_GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"


def _records(graph: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Normalize IDs and exclude dangling edges rather than emit invalid XML."""
    nodes = []
    ids: set[str] = set()
    for raw in graph.get("nodes", []):
        if "id" not in raw:
            raise ValueError("Every graph node must have an id")
        node = dict(raw, id=str(raw["id"]))
        if node["id"] in ids:
            raise ValueError(f"Duplicate graph node id: {node['id']}")
        ids.add(node["id"])
        nodes.append(node)
    edges = [
        dict(edge, source=str(edge["source"]), target=str(edge["target"]))
        for edge in graph.get("edges", [])
        if str(edge.get("source")) in ids and str(edge.get("target")) in ids
    ]
    return nodes, edges


def _value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _xml_text(value: Any) -> str:
    # XML 1.0 forbids these control characters even when entity-escaped.
    return "".join(
        char if char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF
        or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF
        else "\ufffd"
        for char in _value(value)
    )


def _graphml(graph: dict, nodes: list[dict], edges: list[dict]) -> str:
    ET.register_namespace("", _GRAPHML_NS)
    root = ET.Element(f"{{{_GRAPHML_NS}}}graphml")
    keys: dict[tuple[str, str], str] = {}
    fields = {
        "node": sorted({str(key) for node in nodes for key in node}),
        "edge": sorted({str(key) for edge in edges for key in edge} - {"source", "target"}),
        "graph": ["metadata"],
    }
    for scope, names in fields.items():
        for name in names:
            key_id = f"k{len(keys)}"
            keys[scope, name] = key_id
            ET.SubElement(root, "key", {
                "id": key_id, "for": scope, "attr.name": _xml_text(name), "attr.type": "string",
            })
    body = ET.SubElement(root, "graph", {"id": "columbus", "edgedefault": "directed"})
    metadata = {key: value for key, value in graph.items() if key not in {"nodes", "edges"}}
    metadata["omitted_dangling_edges"] = len(graph.get("edges", [])) - len(edges)
    ET.SubElement(body, "data", {"key": keys["graph", "metadata"]}).text = _xml_text(metadata)
    # Generated XML IDs also support source IDs containing whitespace or punctuation.
    xml_ids = {node["id"]: f"n{index}" for index, node in enumerate(nodes)}
    for node in nodes:
        element = ET.SubElement(body, "node", {"id": xml_ids[node["id"]]})
        for key, value in node.items():
            ET.SubElement(element, "data", {"key": keys["node", str(key)]}).text = _xml_text(value)
    for index, edge in enumerate(edges):
        element = ET.SubElement(body, "edge", {
            "id": f"e{index}", "source": xml_ids[edge["source"]], "target": xml_ids[edge["target"]],
        })
        for key, value in edge.items():
            if key not in {"source", "target"}:
                ET.SubElement(element, "data", {"key": keys["edge", str(key)]}).text = _xml_text(value)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _mermaid_label(value: Any) -> str:
    # Mermaid supports decimal entities. Encode syntax delimiters after '#', so
    # names cannot end a quoted label or inject directives, links, or new nodes.
    return (_value(value).replace("#", "#35;").replace("&", "#38;")
            .replace('"', "#34;").replace("<", "#60;").replace(">", "#62;")
            .replace("\\", "#92;").replace("\r", " ").replace("\n", " ")
            .replace("|", "#124;").replace("`", "#96;"))


def _mermaid(nodes: list[dict], edges: list[dict]) -> str:
    shown = nodes[:MERMAID_NODE_LIMIT]
    ids = {node["id"]: f"n{index}" for index, node in enumerate(shown)}
    shown_edges = [edge for edge in edges if edge["source"] in ids and edge["target"] in ids][:MERMAID_EDGE_LIMIT]
    lines = ["flowchart TD", "  %% Solid edges: syntax/static candidates; dotted edges: heuristic/unresolved."]
    if len(shown) != len(nodes) or len(shown_edges) != len(edges):
        lines.append(f"  %% TRUNCATED: showing {len(shown)}/{len(nodes)} nodes and {len(shown_edges)}/{len(edges)} edges.")
    for node in shown:
        label = node.get("qualname") or node.get("name") or node.get("path") or node["id"]
        label = f"{label} ({node.get('kind', 'symbol')})"
        lines.append(f'  {ids[node["id"]]}["{_mermaid_label(label)}"]')
    for edge in shown_edges:
        confidence = edge.get("confidence", "unknown")
        numeric_uncertain = isinstance(confidence, (float, int)) and (not math.isfinite(confidence) or confidence < 1)
        uncertain = numeric_uncertain or str(confidence) not in {"syntactic", "resolved_static", "resolved", "1", "1.0"}
        arrow = "-.->" if uncertain else "-->"
        label = f"{edge.get('kind', 'related')} · {confidence}"
        lines.append(f'  {ids[edge["source"]]} {arrow}|"{_mermaid_label(label)}"| {ids[edge["target"]]}')
    return "\n".join(lines) + "\n"


def _html(graph: dict, nodes: list[dict], edges: list[dict]) -> str:
    node_fields = ("id", "path", "name", "qualname", "kind", "start_line", "end_line")
    edge_fields = ("source", "target", "kind", "confidence", "evidence", "path", "line")
    shown_nodes = [{key: node[key] for key in node_fields if key in node} for node in nodes[:HTML_NODE_LIMIT]]
    ids = {node["id"] for node in shown_nodes}
    shown_edges = [
        {key: edge[key] for key in edge_fields if key in edge}
        for edge in edges if edge["source"] in ids and edge["target"] in ids
    ][:HTML_EDGE_LIMIT]
    data = {
        "nodes": shown_nodes, "edges": shown_edges,
        "total_nodes": len(nodes), "total_edges": len(graph.get("edges", [])),
        "omitted_dangling_edges": len(graph.get("edges", [])) - len(edges),
        "truncated": bool(graph.get("truncated", False)),
        **{key: graph[key] for key in (
            "revision", "freshness", "indexed_at", "git_head_at_index", "center", "direction", "hops",
        ) if key in graph},
    }
    # Script elements are raw text in HTML; JSON escaping alone does NOT stop
    # </script>. Escape delimiters, including data in IDs, names, and evidence.
    payload = (json.dumps(data, ensure_ascii=True, separators=(",", ":"), default=str)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return _HTML.replace("__COLUMBUS_GRAPH_JSON__", payload)


def render_graph(graph: dict, format: str) -> str:
    """Render ``nodes``/``edges`` as HTML, GraphML, or Mermaid.

    HTML is an offline metadata snapshot with a bounded neighborhood view.
    GraphML preserves the full graph and arbitrary metadata. Mermaid caps the
    graph at 80 nodes and 160 edges, with a comment when it truncates output.
    Dangling edges are omitted and counted in HTML/GraphML metadata.
    """
    format = format.lower()
    if format not in {"html", "graphml", "mermaid"}:
        raise ValueError(f"Unsupported graph format: {format}")
    nodes, edges = _records(graph)
    if format == "graphml":
        return _graphml(graph, nodes, edges)
    if format == "mermaid":
        return _mermaid(nodes, edges)
    return _html(graph, nodes, edges)


_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>Columbus · Code graph</title>
<style>
:root{color-scheme:dark;--bg:#0c1019;--panel:#121925;--raised:#1a2435;--line:#29354a;--fg:#e7edf7;--muted:#a3b2c8;--mint:#69dec0;--blue:#8cb9ff;--amber:#efbb67}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button,input,select{font:inherit;color:inherit}button,select,input{border:1px solid var(--line);background:var(--panel);border-radius:7px}button{cursor:pointer}button:hover{background:var(--raised)}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--blue);outline-offset:3px}header{padding:22px 28px;border-bottom:1px solid var(--line);display:flex;gap:24px;align-items:center;flex-wrap:wrap}h1{font-size:21px;margin:0;letter-spacing:-.5px}h1 span{color:var(--mint)}header p{margin:0;color:var(--muted);font-size:13px}.status{margin-left:auto;font-variant-numeric:tabular-nums}.workspace{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:calc(100vh - 82px)}aside{padding:22px 16px;border-right:1px solid var(--line);background:var(--panel)}label{display:block;font-size:12px;color:var(--muted);margin-bottom:7px}input[type=search]{width:100%;padding:10px 12px;background:var(--bg)}#node-count{color:var(--muted);font-size:12px;margin:14px 0 8px}#node-list{display:grid;gap:4px;max-height:calc(100vh - 246px);overflow:auto}button.node-row{padding:10px;text-align:left;border:1px solid transparent;background:transparent;overflow-wrap:anywhere}.node-row[aria-pressed=true]{background:var(--raised);border-color:var(--line)}.node-row strong{display:block;font-size:13px;font-weight:500}.node-row small{display:block;color:var(--muted);font-size:11px;margin-top:3px}.main{padding:26px 28px;min-width:0}.eyebrow{text-transform:uppercase;letter-spacing:1.7px;font-size:11px;color:var(--mint);margin-bottom:9px}h2{font-size:23px;line-height:1.3;overflow-wrap:anywhere;font-weight:500;margin:0 0 8px}.location{font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0 12px}.controls select{padding:8px 12px;min-width:154px}.controls label{margin:0}.controls label span{display:block;margin-bottom:5px}.view{border:1px solid var(--line);border-radius:11px;overflow:hidden;background:linear-gradient(160deg,#131c2b,#0e1520)}.graph-scroll{overflow:auto;max-height:650px;min-height:360px}#graph{display:block;width:100%;min-width:720px}.legend{padding:11px 16px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);display:flex;gap:18px;flex-wrap:wrap}.legend span:before{content:"";width:24px;border-top:2px solid var(--blue);display:inline-block;vertical-align:middle;margin-right:7px}.legend .uncertain:before{border-color:var(--amber);border-top-style:dashed}#notice{color:var(--amber);font-size:12px;margin:12px 0;min-height:18px}.details{display:grid;grid-template-columns:minmax(200px,.8fr) minmax(0,1.2fr);gap:24px;margin-top:24px}.details h3{font-size:13px;font-weight:500;margin:0 0 12px}.details p{font-size:12px;color:var(--muted);overflow-wrap:anywhere}dl{display:grid;grid-template-columns:80px minmax(0,1fr);font-size:12px;margin:0;gap:8px 14px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}#relations{display:grid;gap:6px;max-height:360px;overflow:auto}.edge-row{padding:12px 13px;text-align:left;background:var(--panel)}.edge-row b{display:block;font-size:12px;font-weight:500;overflow-wrap:anywhere}.edge-row small{display:block;font-size:11px;color:var(--muted);margin-top:4px;overflow-wrap:anywhere}.edge-row.selected{border-color:var(--mint)}#evidence{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--fg);background:var(--panel);border:1px solid var(--line);padding:14px;border-radius:8px;margin-top:14px;font:12px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace}.footnote{color:var(--muted);font-size:11px;margin-top:24px}.empty{padding:22px 0;color:var(--muted)}
@media(max-width:1000px){.workspace{grid-template-columns:230px minmax(0,1fr)}.main{padding:24px 18px}.details{grid-template-columns:1fr}}
@media(max-width:650px){header{padding:18px;gap:8px 20px}.status{margin-left:0;width:100%}.workspace{display:block}aside{border-right:0;border-bottom:1px solid var(--line);padding:16px 18px}#node-list{max-height:190px;grid-template-columns:1fr 1fr}.main{padding:24px 18px}.controls select{min-width:130px}.graph-scroll{max-height:540px}h2{font-size:20px}}
</style>
</head>
<body>
<header><h1><span>Columbus</span></h1><p>Explore code through its relationships</p><p class="status" id="stats"></p><p id="snapshot" style="width:100%;font-size:12px;overflow-wrap:anywhere"></p></header>
<div class="workspace">
<aside><label for="search">Find a symbol or file</label><input id="search" type="search" placeholder="Name, path, or symbol ID" autocomplete="off"><p id="node-count" aria-live="polite"></p><div id="node-list" aria-label="Symbols"></div></aside>
<main class="main">
<div class="eyebrow">One-hop neighborhood</div><h2 id="title">Choose a symbol</h2><div class="location" id="location"></div>
<div class="controls"><label for="direction"><span>Direction</span><select id="direction"><option value="both">Incoming + outgoing</option><option value="incoming">Incoming only</option><option value="outgoing">Outgoing only</option></select></label><label for="edge-kind"><span>Relationship</span><select id="edge-kind"><option value="all">All relationships</option></select></label></div>
<div class="view"><div class="graph-scroll"><svg id="graph" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Selected symbol and its incoming and outgoing relationships"></svg></div><div class="legend"><span>Syntax / static candidate</span><span class="uncertain">Heuristic / unresolved</span></div></div>
<p id="notice" role="status"></p>
<div class="details"><section><h3>Symbol</h3><dl id="metadata"></dl><p>Locations refer to the indexed repository snapshot. Source files are not embedded in this export.</p><div id="evidence" hidden></div></section><section><h3 id="relations-title">Relationships</h3><div id="relations"></div></section></div>
<p class="footnote">Offline snapshot · Select a node to explore its neighbors. Select a relationship to inspect evidence. Static candidates are not proof of runtime behavior.</p>
</main></div>
<script id="columbus-data" type="application/json">__COLUMBUS_GRAPH_JSON__</script>
<script>
"use strict";
(() => {
  const graph = JSON.parse(document.getElementById("columbus-data").textContent);
  const $ = id => document.getElementById(id);
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const adjacent = new Map(graph.nodes.map(node => [node.id, []]));
  graph.edges.forEach((edge, index) => {
    edge.index = index;
    if (adjacent.has(edge.source)) adjacent.get(edge.source).push(edge);
    if (edge.target !== edge.source && adjacent.has(edge.target)) adjacent.get(edge.target).push(edge);
  });
  const label = node => String(node.qualname || node.name || node.path || node.id);
  const pretty = value => typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "—");
  const location = node => node.path ? `${node.path}${node.start_line ? ':' + node.start_line : ''}${node.end_line && node.end_line !== node.start_line ? '–' + node.end_line : ''}` : "No repository source location";
  const uncertain = edge => typeof edge.confidence === "number" ? edge.confidence < 1 : !["syntactic", "resolved_static", "resolved", "1", "1.0"].includes(String(edge.confidence));
  const confidenceLabels = new Map([["syntactic","syntactic fact"],["resolved_static","static candidate"],["heuristic","heuristic candidate"]]);
  const confidence = edge => confidenceLabels.get(edge.confidence) || pretty(edge.confidence ?? "unknown");
  const shorten = (text, limit) => text.length > limit ? text.slice(0, limit - 1) + "…" : text;
  const element = (tag, text, className) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if(className) el.className = className; return el; };
  const svgElement = (tag, attributes, text) => { const el = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attributes || {}).forEach(([key,value]) => el.setAttribute(key,String(value))); if(text !== undefined) el.textContent = text; return el; };
  let selected = nodes.has(graph.center) ? graph.center : graph.nodes.find(node => !["file","external","unresolved"].includes(node.kind))?.id || graph.nodes[0]?.id;
  let displayedEdges = [];
  const baseNotices = [];
  if(graph.truncated) baseNotices.push("The input graph was truncated before export. Counts describe the supplied snapshot, not the full repository.");
  const freshness = String(graph.freshness ?? "unknown");
  if(freshness === "stale") baseNotices.push("The index reports stale source files. Refresh it before using these locations for edits.");
  else if(freshness !== "checked_clean" && freshness !== "source_hash_verified") baseNotices.push("Working tree freshness is not verified by this graph export.");
  if(graph.nodes.length < graph.total_nodes || graph.edges.length < graph.total_edges) baseNotices.push(`Export includes ${graph.nodes.length.toLocaleString()}/${graph.total_nodes.toLocaleString()} nodes and ${graph.edges.length.toLocaleString()}/${graph.total_edges.toLocaleString()} edges. Use a focused graph export for omitted code.`);
  if(graph.omitted_dangling_edges) baseNotices.push(`${graph.omitted_dangling_edges} edges with missing endpoints omitted.`);
  $("stats").textContent = `${graph.total_nodes.toLocaleString()} nodes · ${graph.total_edges.toLocaleString()} relationships`;
  $("snapshot").textContent = `Revision: ${pretty(graph.revision ?? 'not supplied')} · Reported freshness: ${pretty(graph.freshness ?? 'unknown')}${graph.indexed_at ? ' · Indexed: ' + pretty(graph.indexed_at) : ''}`;
  [...new Set(graph.edges.map(edge => edge.kind || "related"))].sort().forEach(kind => { const option = element("option",kind); option.value = kind; $("edge-kind").appendChild(option); });

  function renderList() {
    const query = $("search").value.toLocaleLowerCase().trim();
    const matches = graph.nodes.filter(node => [node.id,node.name,node.qualname,node.path].some(value => String(value || "").toLocaleLowerCase().includes(query)));
    $("node-list").replaceChildren();
    $("node-count").textContent = `${matches.length.toLocaleString()} matches${matches.length > 150 ? ' · showing first 150; refine search' : ''}`;
    matches.slice(0,150).forEach(node => {
      const button = element("button", undefined, "node-row"); button.type = "button"; button.setAttribute("aria-pressed",String(node.id === selected));
      button.appendChild(element("strong",label(node))); button.appendChild(element("small",`${node.kind || 'symbol'} · ${location(node)}`));
      button.addEventListener("click",() => select(node.id)); $("node-list").appendChild(button);
    });
    if(!matches.length) $("node-list").appendChild(element("p","No matching symbols.","empty"));
  }
  function select(id) { selected = id; renderList(); renderNeighborhood(); }
  function showEvidence(edge) {
    const path = edge.path || nodes.get(edge.source)?.path;
    const at = path ? `${path}${edge.line ? ':' + edge.line : ''}` : "No source location recorded";
    $("evidence").hidden = false;
    $("evidence").textContent = `${edge.kind || 'related'} · ${confidence(edge)}\n${at}\n\n${pretty(edge.evidence || 'No evidence text recorded.')}`;
    document.querySelectorAll(".edge-row").forEach(row => row.classList.toggle("selected",row.dataset.edge === String(edge.index)));
  }
  function renderNeighborhood() {
    const node = nodes.get(selected);
    $("metadata").replaceChildren(); $("relations").replaceChildren(); $("evidence").hidden = true;
    if(!node) { $("title").textContent = "No indexed symbols"; $("location").textContent = "Index a supported repository, then export its graph."; $("notice").textContent = baseNotices.join(" "); draw([],[],[]); return; }
    $("title").textContent = label(node); $("location").textContent = location(node);
    [["Kind",node.kind || "symbol"],["Location",location(node)],["Symbol ID",node.id]].forEach(([key,value]) => { $("metadata").appendChild(element("dt",key)); $("metadata").appendChild(element("dd",pretty(value))); });
    const direction = $("direction").value, kind = $("edge-kind").value;
    const matching = adjacent.get(selected).filter(edge => (kind === "all" || (edge.kind || "related") === kind) && (direction === "both" || (direction === "incoming" ? edge.target === selected : edge.source === selected)));
    const neighborIds = [...new Set(matching.map(edge => edge.source === selected ? edge.target : edge.source))].filter(id => id !== selected);
    const included = new Set(neighborIds.slice(0,24)); included.add(selected);
    displayedEdges = matching.filter(edge => included.has(edge.source) && included.has(edge.target)).slice(0,80);
    const incoming = [], outgoing = [];
    neighborIds.slice(0,24).forEach(id => { (displayedEdges.some(edge => edge.source === selected && edge.target === id) ? outgoing : incoming).push(nodes.get(id)); });
    const notices = [...baseNotices];
    if(neighborIds.length > 24 || displayedEdges.length < matching.length) notices.push(`Neighborhood capped: showing ${Math.min(neighborIds.length,24)}/${neighborIds.length} neighbors and ${displayedEdges.length}/${matching.length} relationships. Narrow the direction or relationship filter.`);
    $("notice").textContent = notices.join(" ");
    $("relations-title").textContent = `Relationships · ${displayedEdges.length}${displayedEdges.length < matching.length ? '/' + matching.length : ''}`;
    displayedEdges.forEach(edge => {
      const button = element("button",undefined,"edge-row"); button.type = "button"; button.dataset.edge = String(edge.index);
      button.appendChild(element("b",`${label(nodes.get(edge.source))} → ${label(nodes.get(edge.target))}`));
      button.appendChild(element("small",`${edge.kind || 'related'} · ${confidence(edge)}${edge.path ? ' · ' + edge.path + (edge.line ? ':' + edge.line : '') : ''}`));
      button.addEventListener("click",() => showEvidence(edge)); $("relations").appendChild(button);
    });
    if(!displayedEdges.length) $("relations").appendChild(element("p","No relationships match these filters.","empty"));
    draw(node,incoming,outgoing);
  }
  function draw(center,incoming,outgoing) {
    const svg = $("graph"); svg.replaceChildren();
    const width = 900, height = Math.max(390,Math.max(incoming.length,outgoing.length) * 82 + 100);
    svg.setAttribute("viewBox",`0 0 ${width} ${height}`); svg.style.height = `${height}px`;
    // Keep the selected node visible in large neighborhoods; the bounded
    // graph viewport can still scroll to every displayed neighbor.
    requestAnimationFrame(() => { svg.parentElement.scrollTop = Math.max(0,(height - svg.parentElement.clientHeight)/2); });
    svg.appendChild(svgElement("title",{},"One-hop code relationships"));
    const defs = svgElement("defs");
    [["known","#8cb9ff"],["uncertain","#efbb67"]].forEach(([id,color]) => {const marker = svgElement("marker",{id:'arrow-' + id,viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:7,markerHeight:7,orient:"auto-start-reverse"});marker.appendChild(svgElement("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:color}));defs.appendChild(marker);}); svg.appendChild(defs);
    if(!center.id) { svg.appendChild(svgElement("text",{x:450,y:190,'text-anchor':'middle',fill:'#a3b2c8','font-size':16},"No symbols in this snapshot")); return; }
    const positions = new Map([[center.id,{x:450,y:height/2,node:center}]]);
    const place = (items,x) => items.forEach((node,index) => positions.set(node.id,{x,y:(height - (items.length - 1) * 82)/2 + index * 82,node}));
    place(incoming,155); place(outgoing,745);
    [[155,"INCOMING"],[450,"SELECTED SYMBOL"],[745,"OUTGOING"]].forEach(([x,text]) => svg.appendChild(svgElement("text",{x,y:32,'text-anchor':'middle',fill:'#a3b2c8','font-size':11,'letter-spacing':1.5},text)));
    displayedEdges.forEach(edge => {
      const start = positions.get(edge.source), end = positions.get(edge.target); if(!start || !end) return;
      const right = end.x >= start.x, fromX = start.x + (right ? 104 : -104), toX = end.x + (right ? -108 : 108), bend = (fromX + toX)/2;
      const d = edge.source === edge.target ? `M ${start.x-45} ${start.y-29} C ${start.x-115} ${start.y-115},${start.x+115} ${start.y-115},${start.x+45} ${start.y-29}` : `M ${fromX} ${start.y} C ${bend} ${start.y},${bend} ${end.y},${toX} ${end.y}`;
      const isUncertain = uncertain(edge);
      const path = svgElement("path",{d,fill:"none",stroke:isUncertain ? '#efbb67' : '#8cb9ff','stroke-width':1.5,'stroke-opacity':.7,'marker-end':`url(#arrow-${isUncertain ? 'uncertain' : 'known'})`}); if(isUncertain) path.setAttribute("stroke-dasharray","5 4");
      path.appendChild(svgElement("title",{},`${edge.kind || 'related'} · ${confidence(edge)}`)); svg.appendChild(path);
      const hit = svgElement("path",{d,fill:"none",stroke:"transparent",'stroke-width':16,cursor:'pointer'});hit.addEventListener("click",() => showEvidence(edge));svg.appendChild(hit);
    });
    positions.forEach(({x,y,node}) => {
      const active = node.id === selected, external = ["external","unresolved"].includes(node.kind);
      const group = svgElement("g",{transform:`translate(${x},${y})`,cursor:"pointer",role:"button",tabindex:0,'aria-label':`Explore ${label(node)}`});
      const rect = svgElement("rect",{x:-104,y:-29,width:208,height:58,rx:9,fill:active ? '#1b3838' : '#192435',stroke:active ? '#69dec0' : external ? '#efbb67' : '#34465e','stroke-width':active ? 1.6 : 1});if(external) rect.setAttribute("stroke-dasharray","4 3"); group.appendChild(rect);
      group.appendChild(svgElement("text",{x:0,y:-3,'text-anchor':'middle',fill:'#e7edf7','font-family':'system-ui,sans-serif','font-size':12},shorten(label(node),27)));
      group.appendChild(svgElement("text",{x:0,y:16,'text-anchor':'middle',fill:'#a3b2c8','font-family':'system-ui,sans-serif','font-size':11},node.kind || 'symbol'));
      group.appendChild(svgElement("title",{},`${label(node)}\n${location(node)}`));
      group.addEventListener("click",() => select(node.id));group.addEventListener("keydown",event => {if(event.key === 'Enter' || event.key === ' '){event.preventDefault();select(node.id);}});svg.appendChild(group);
    });
  }
  $("search").addEventListener("input",renderList); $("direction").addEventListener("change",renderNeighborhood); $("edge-kind").addEventListener("change",renderNeighborhood);
  renderList(); renderNeighborhood();
})();
</script>
</body></html>
'''
