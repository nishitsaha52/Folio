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
    evidence = {e["id"]: e for e in analysis["evidence"]}
    nodes = {}
    edges = []
    for edge in analysis["edges"][:100]:
        for path in (edge["source"], edge["target"]):
            nodes[stable_id("N", path)] = path
        edges.append((stable_id("N", edge["source"]), stable_id("N", edge["target"]), "imports"))
    if not nodes:
        for item in analysis["inventory"][:12]:
            if item["category"] == "source":
                nodes[stable_id("N", item["path"])] = item["path"]
    graphs = {
        "Architecture_Diagram": (
            nodes,
            edges,
            "Verified code dependencies; deployment topology requires review",
        )
    }
    context_nodes = {"application": analysis.get("repository", "Application")}
    context_edges = []
    api = [f for f in analysis["findings"] if f["kind"] == "api"]
    integrations = [f for f in analysis["findings"] if f["kind"] == "integration"]
    if api:
        context_nodes["client"] = "API caller (inferred actor)"
        context_edges.append(("client", "application", "declared API input"))
    for item in integrations[:12]:
        context_nodes[item["id"]] = item["title"]
        context_edges.append(("application", item["id"], "HTTPS call declaration"))
    graphs["DFD_Level_0"] = (
        context_nodes,
        context_edges,
        "Context inferred from API and integration declarations",
    )
    process_nodes, process_edges = {}, []
    for item in api[:35]:
        path = evidence[item["evidence_ids"][0]]["path"]
        nid = stable_id("N", path)
        process_nodes[item["id"]] = item["title"]
        process_nodes[nid] = path
        process_edges.append((item["id"], nid, "handler declared in"))
    for item in integrations[:12]:
        path = evidence[item["evidence_ids"][0]]["path"]
        nid = stable_id("N", path)
        process_nodes[nid] = path
        process_nodes[item["id"]] = item["title"]
        process_edges.append((nid, item["id"], "HTTPS call"))
    graphs["DFD_Level_1"] = (
        process_nodes,
        process_edges,
        "Declared process boundaries; runtime payload movement is unverified",
    )
    detailed_nodes, detailed_edges = {}, []
    for item in api[:20]:
        handler = item["metadata"].get("handler")
        if not handler:
            continue
        path = evidence[item["evidence_ids"][0]]["path"]
        nid = stable_id("N", path, handler)
        detailed_nodes[item["id"]] = item["title"]
        detailed_nodes[nid] = f"{path}: {handler}"
        detailed_edges.append((item["id"], nid, "declared handler"))
    graphs["DFD_Level_2"] = (
        detailed_nodes,
        detailed_edges,
        "Handler-level detail supported by route declarations; deeper flows require review",
    )
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
        f'<text x="30" y="28" font-family="Arial" font-size="16" fill="#172033">{html.escape(name.replace("_", " "))}</text>',
        f'<text x="30" y="52" font-family="Arial" font-size="11" fill="#475569">{html.escape(note)}</text>',
    ]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=13)
    draw.text((30, 15), name.replace("_", " "), fill="#172033", font=font)
    draw.text((30, 40), note, fill="#475569", font=ImageFont.load_default(size=11))
    for index, (source, relation, target) in enumerate(rows):
        y = 70 + index * 86
        for x, value in ((30, source), (650, target)):
            if not value:
                continue
            clean = label(value)
            lines = [clean[i : i + 49] for i in range(0, len(clean), 49)]
            svg.append(
                f'<rect x="{x}" y="{y}" width="420" height="62" rx="6" fill="#f1f5f9" stroke="#94a3b8"/>'
            )
            draw.rounded_rectangle((x, y, x + 420, y + 62), radius=6, fill="#f1f5f9", outline="#94a3b8")
            for j, line in enumerate(lines[:2]):
                svg.append(
                    f'<text x="{x + 12}" y="{y + 25 + j * 18}" font-family="Arial" font-size="13" fill="#172033">{html.escape(line)}</text>'
                )
                draw.text((x + 12, y + 15 + j * 18), line, fill="#172033", font=font)
        if target:
            svg.append(f'<path d="M450 {y + 31} H640 l-8 -5 m8 5 l-8 5" fill="none" stroke="#64748b"/>')
            svg.append(
                f'<text x="460" y="{y + 20}" font-family="Arial" font-size="11" fill="#475569">{html.escape(relation)}</text>'
            )
            draw.line((450, y + 31, 640, y + 31), fill="#64748b", width=2)
            draw.polygon([(640, y + 31), (632, y + 26), (632, y + 36)], fill="#64748b")
            draw.text((460, y + 10), relation, fill="#475569", font=ImageFont.load_default(size=11))
    svg.append("</svg>")
    (directory / f"{name}.svg").write_text("\n".join(svg), encoding="utf-8")
    image.save(directory / f"{name}.png")
