"""Evidence-derived Mermaid/Graphviz diagrams and deterministic local SVG/PNG exports."""

import html
import re
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from docagent.analysis import stable_id


def label(value):
    return re.sub(r"[^\w ./:{}()@-]", " ", value)[:100]


def graph_sets(analysis):
    from docagent.report_content import component
    from docagent.reporting import resource, supporting_path, words

    evidence = {e["id"]: e for e in analysis["evidence"]}
    include_supporting = analysis.get("report_scope", {}).get("includes_supporting", False)
    primary_routes = [f for f in analysis["findings"] if f["kind"] == "api" and
                      not supporting_path(evidence[f["evidence_ids"][0]]["path"])]
    routes = primary_routes or [f for f in analysis["findings"] if f["kind"] == "api"]
    nodes, edges, seen = {}, [], set()
    for edge in analysis["edges"]:
        if not include_supporting and (supporting_path(edge["source"]) or supporting_path(edge["target"])):
            continue
        source, target = component(edge["source"]), component(edge["target"])
        if source == target or (source, target) in seen:
            continue
        seen.add((source, target))
        sid, tid = stable_id("N", source), stable_id("N", target)
        nodes[sid], nodes[tid] = source, target
        edges.append((sid, tid, "imports"))
    displayed = edges[:12]
    used = {node for edge in displayed for node in edge[:2]}
    nodes = {key: value for key, value in nodes.items() if key in used}
    if not nodes:
        nodes = {stable_id("N", item["path"]): component(item["path"]) for item in analysis["inventory"]
                 if item["category"] == "source" and (include_supporting or not supporting_path(item["path"]))}
        nodes = dict(list(nodes.items())[:8])
    graphs = {"Architecture_Diagram": (nodes, displayed,
              f"Source dependencies by responsibility; {len(displayed)} of {len(edges)} grouped relationships shown")}
    context_nodes = {"application": analysis.get("repository", "Application")}
    context_edges = []
    if routes:
        context_nodes["client"] = "Application client"
        context_edges.append(("client", "application", "declared interface"))
    for finding in [f for f in analysis["findings"] if f["kind"] == "integration"][:4]:
        path = evidence[finding["evidence_ids"][0]]["path"]
        if supporting_path(path):
            continue
        context_nodes[finding["id"]] = finding["title"]
        context_edges.append(("application", finding["id"], "literal HTTPS call"))
    graphs["DFD_Level_0"] = (context_nodes, context_edges,
                              "Declared context; effective access and payloads need verification")
    groups = {}
    for finding in routes:
        groups.setdefault(resource(finding["metadata"].get("route", "/")), []).append(finding)
    process_nodes, process_edges, detail_nodes, detail_edges = {}, [], {}, []
    for key, members in sorted(groups.items()):
        gid = stable_id("N", "capability", key)
        process_nodes[gid] = words(key).capitalize()
        targets = {component(evidence[f["evidence_ids"][0]]["path"]) for f in members}
        for target in sorted(targets):
            tid = stable_id("N", target)
            process_nodes[tid] = target
            process_edges.append((gid, tid, f"{len(members)} declared operations"))
        # One representative handler per capability; the appendix retains all routes.
        finding = members[0]
        handler = finding["metadata"].get("handler")
        if handler:
            hid = stable_id("N", key, handler)
            detail_nodes[gid] = finding["title"]
            detail_nodes[hid] = words(handler.split(".")[-1])
            detail_edges.append((gid, hid, "declared handler"))
    graphs["DFD_Level_1"] = (process_nodes, process_edges,
                              "Application interfaces grouped by resource; examples excluded when primary routes exist")
    graphs["DFD_Level_2"] = (detail_nodes, detail_edges,
                              "One representative handler per capability; full route list in API Reference")
    return graphs


def mermaid(nodes, edges, note):
    lines = ["flowchart LR", f"  %% {note}"]
    if not nodes:
        lines.append('  missing["Insufficient code evidence for this diagram"]')
    for nid, text in nodes.items():
        lines.append(f'  {nid.replace("-", "_")}["{label(text)}"]')
    for source, target, text in edges:
        lines.append(f'  {source.replace("-", "_")} -->|"{label(text)}"| {target.replace("-", "_")}')
    return "\n".join(lines) + "\n"


def export_graph(directory, name, graph):
    directory.mkdir(parents=True, exist_ok=True)
    nodes, edges, note = graph
    if not nodes:
        nodes = {"missing": "Insufficient code evidence"}
    (directory / f"{name}.mmd").write_text(mermaid(nodes, edges, note), encoding="utf-8")
    dot_lines = [
        'digraph G { rankdir=LR; graph [bgcolor="white"]; node [shape=box, style="rounded", fontname="Arial"];'
    ]
    for nid, text in nodes.items():
        dot_lines.append(f'"{nid}" [label="{label(text)}"];')
    for source, target, text in edges:
        dot_lines.append(f'"{source}" -> "{target}" [label="{label(text)}"];')
    dot_lines.append("}")
    dot = directory / f"{name}.dot"
    dot.write_text("\n".join(dot_lines), encoding="utf-8")
    if shutil.which("dot"):
        try:
            for fmt in ("svg", "png"):
                subprocess.run(
                    ["dot", f"-T{fmt}", str(dot), "-o", str(directory / f"{name}.{fmt}")],
                    timeout=30,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return
        except (subprocess.SubprocessError, OSError):
            pass
    # Portable fallback: same nodes and relations, laid out without executing repository content.
    # Each edge occupies a separate row to keep exports legible even without Graphviz.
    rows = [(nodes[s], text, nodes[t]) for s, t, text in edges]
    if not rows:
        rows = [(value, "", "") for value in nodes.values()]
    width, height = 1100, 90 + len(rows) * 86
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="30" y="28" font-family="Arial" font-size="24" fill="#172033">{html.escape(name.replace("_", " "))}</text>',
        f'<text x="30" y="52" font-family="Arial" font-size="17" fill="#475569">{html.escape(note)}</text>',
    ]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=21)
    draw.text((30, 15), name.replace("_", " "), fill="#172033", font=font)
    draw.text((30, 40), note, fill="#475569", font=ImageFont.load_default(size=17))
    for index, (source, relation, target) in enumerate(rows):
        y = 70 + index * 86
        for x, value in ((30, source), (650, target)):
            if not value:
                continue
            clean = label(value)
            lines = [clean[i : i + 34] for i in range(0, len(clean), 34)]
            svg.append(
                f'<rect x="{x}" y="{y}" width="420" height="62" rx="6" fill="#f1f5f9" stroke="#94a3b8"/>'
            )
            draw.rounded_rectangle((x, y, x + 420, y + 62), radius=6, fill="#f1f5f9", outline="#94a3b8")
            for j, line in enumerate(lines[:2]):
                svg.append(
                    f'<text x="{x + 12}" y="{y + 25 + j * 25}" font-family="Arial" font-size="21" fill="#172033">{html.escape(line)}</text>'
                )
                draw.text((x + 12, y + 9 + j * 25), line, fill="#172033", font=font)
        if target:
            svg.append(f'<path d="M450 {y + 31} H640 l-8 -5 m8 5 l-8 5" fill="none" stroke="#64748b"/>')
            svg.append(
                f'<text x="460" y="{y + 20}" font-family="Arial" font-size="16" fill="#475569">{html.escape(relation)}</text>'
            )
            draw.line((450, y + 31, 640, y + 31), fill="#64748b", width=2)
            draw.polygon([(640, y + 31), (632, y + 26), (632, y + 36)], fill="#64748b")
            draw.text((460, y + 8), relation, fill="#475569", font=ImageFont.load_default(size=16))
    svg.append("</svg>")
    (directory / f"{name}.svg").write_text("\n".join(svg), encoding="utf-8")
    image.save(directory / f"{name}.png")
