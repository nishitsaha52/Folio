"""Seven consistent deliverables generated from a single versioned analysis snapshot."""

import json
import logging
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from docagent.diagrams import export_graph, graph_sets
from docagent.document_renderers import markdown, write_docx, write_pdf
from docagent.report_content import build_sections
from docagent.security import redact_object

logger = logging.getLogger(__name__)

DOCUMENT_PATHS = {
    "srs": ("01-requirements", "Software_Requirements_Specification", "Software Requirements Specification"),
    "requirements_signoff": ("01-requirements", "Requirements_Signoff", "Requirements Review and Signoff"),
    "test_cases": (
        "02-testing",
        "Test_Cases_and_UAT_Report",
        "Test Cases and User Acceptance Testing Report",
    ),
    "uat_signoff": ("02-testing", "Application_UAT_Signoff", "Application Acceptance and UAT Signoff"),
    "architecture": ("03-architecture", "System_Architecture", "System Architecture"),
    "data_flow": ("04-data-flow", "Data_Flow_Document", "Application Data Flow"),
    "technology": ("05-technology-stack", "Technology_Stack", "Technology Stack and Dependencies"),
}


def evidence_text(ids, evidence, repository):
    lines = []
    for eid in ids:
        e = evidence[eid]
        if repository.startswith(("local/", "demo/")):
            lines.append(
                f"{eid}: {e['path']}:{e['start_line']}-{e['end_line']} ({e['symbol'] or 'file'}); local snapshot {e['commit']}"
            )
            continue
        url = f"https://github.com/{repository}/blob/{e['commit']}/{quote(e['path'])}#L{e['start_line']}-L{e['end_line']}"
        lines.append(
            f"{eid}: {e['path']}:{e['start_line']}-{e['end_line']} ({e['symbol'] or 'file'}) [{url}]"
        )
    return "\n".join(lines)


def write_rtm(path, analysis, state):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Traceability"
    headers = [
        "Requirement ID",
        "Requirement",
        "Module",
        "Evidence IDs",
        "Test case ID",
        "Test category",
        "Execution status",
        "Result source",
        "Evidence reference",
        "Commit",
        "Expected outcome",
        "Preparation",
        "Actions",
    ]
    sheet.append(headers)
    requirements = {r["id"]: r for r in analysis["requirements"]}
    results = {r["test_case_id"]: r for r in state["results"]}
    for row_number, case in enumerate(analysis["test_cases"], 2):
        req = requirements[case["requirement_id"]]
        result = results.get(case["id"], {})
        values = [
            req["id"],
            req["title"],
            req["module"],
            ", ".join(req["evidence_ids"]),
            case["id"],
            case["category"],
            result.get("status", "unexecuted"),
            result.get("source", "generated"),
            result.get("evidence_reference", ""),
            analysis["commit"],
            case["expected"],
            "\n".join(case["preconditions"]),
            "\n".join(case["steps"]),
        ]
        sheet.append(values)
        # Indexing a whole row also asks openpyxl to scan for max_column.
        # Address the known cells directly so export work stays linear.
        for column_number in range(1, len(values) + 1):
            cell = sheet.cell(row=row_number, column=column_number)
            cell.data_type = "s"  # Prevent spreadsheet formula injection from repository strings.
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="243449")
    covered = {case["requirement_id"] for case in analysis["test_cases"]}
    coverage = workbook.create_sheet("Coverage")
    coverage.append(["Capability", "Requirement ID", "Proposed cases", "Design status"])
    for req in analysis["requirements"]:
        count = sum(case["requirement_id"] == req["id"] for case in analysis["test_cases"])
        coverage.append([req["title"], req["id"], count, "Proposed for review" if req["id"] in covered else "Test design required"])
    for row in coverage:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for column, width in zip("ABCD", (40, 26, 20, 30)):
        coverage.column_dimensions[column].width = width
    coverage.freeze_panes = "A2"
    coverage.auto_filter.ref = coverage.dimensions
    widths = [24, 40, 32, 35, 24, 18, 20, 22, 35, 35, 65, 55, 65]
    from openpyxl.utils import get_column_letter

    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    if sheet.max_row > 1:
        table = Table(displayName="RequirementsTraceability", ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)
    workbook.save(path)


def package_path(root: Path) -> Path:
    return root.with_name(root.name + ".zip")


def export_package(root: Path, analysis, config, state, version, progress=None):
    if package_path(root).exists():
        raise FileExistsError("The output ZIP already exists; choose a new output directory")
    root.mkdir(parents=True, exist_ok=False)
    analysis = redact_object(analysis)
    state = redact_object(state)
    generated = datetime.now(UTC).isoformat()
    metadata = f"Application: {analysis['repository']}\nSource snapshot: {analysis['commit'][:12]} | Document version: {version}\nGenerated: {generated[:10]} | Status: draft for review"
    graphs = graph_sets(analysis)
    diagram_count = int("architecture" in config.documents) + 3 * int("data_flow" in config.documents)
    total = diagram_count + len(config.documents) * (1 + int("docx" in config.formats) + int("pdf" in config.formats)) + 2
    total += int("test_cases" in config.documents or "uat_signoff" in config.documents)
    completed = 0

    def report(message):
        if progress:
            progress(completed, total, message)

    if "architecture" in config.documents:
        report("Drawing architecture diagram")
        export_graph(root / "03-architecture", "Architecture_Diagram", graphs["Architecture_Diagram"])
        completed += 1
    if "data_flow" in config.documents:
        for name in ("DFD_Level_0", "DFD_Level_1", "DFD_Level_2"):
            report("Drawing " + name.replace("_", " "))
            export_graph(root / "04-data-flow", name, graphs[name])
            completed += 1
    previews = {}
    for kind in config.documents:
        logger.info("Document export started document=%s", kind)
        folder, filename, title = DOCUMENT_PATHS[kind]
        directory = root / folder
        directory.mkdir(exist_ok=True)
        sections = build_sections(kind, analysis, state)
        report(f"Writing {title} as Markdown")
        text = markdown(title, metadata, sections)
        previews[kind] = text
        # A text preview is always retained in addition to the selected export formats.
        (directory / f"{filename}.md").write_text(text, encoding="utf-8")
        completed += 1
        if "docx" in config.formats:
            report(f"Writing {title} as Word")
            write_docx(directory / f"{filename}.docx", title, metadata, sections)
            completed += 1
        if "pdf" in config.formats:
            report(f"Writing {title} as PDF")
            write_pdf(directory / f"{filename}.pdf", title, metadata, sections)
            completed += 1
        logger.info("Document export completed document=%s", kind)
    if "test_cases" in config.documents or "uat_signoff" in config.documents:
        (root / "02-testing").mkdir(exist_ok=True)
        report("Writing requirements traceability workbook")
        write_rtm(root / "02-testing" / "Requirements_Traceability_Matrix.xlsx", analysis, state)
        completed += 1
    report("Writing source evidence and coverage reports")
    directory = root / "06-analysis"
    directory.mkdir(exist_ok=True)
    for filename, value in (
        ("Repository_Analysis_Summary.json", analysis),
        ("Evidence_Mapping.json", analysis["evidence"]),
        ("Workflow_and_Approvals.json", state),
        ("Technical_Candidates.json", analysis.get("technical_candidates", {})),
        ("Scope_Report.json", analysis.get("scope", {})),
    ):
        (directory / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    (directory / "Documentation_Gaps.md").write_text(
        "# Documentation Gaps\n\n" + "\n".join(f"- {g}" for g in analysis["gaps"]), encoding="utf-8"
    )
    write_appendices(directory, analysis)
    scope = analysis.get("scope", {})
    scope_lines = ["# Scan Coverage", "", "## Paths that could not be inspected", ""]
    if scope.get("budget_reached"):
        scope_lines.insert(2, "The selected analysis budget was reached. Some additional source files were not inspected.\n")
    for item in scope.get("skipped_files", []):
        code = f" (OS code: {item['code']})" if item.get("code") is not None else ""
        scope_lines.append(f"- {item['path']} — {item['message']}{code}")
    if "scope" not in analysis:
        scope_lines.append("Per-path coverage metadata was not recorded for this older analysis. Start a new analysis to obtain the detailed coverage report.")
    elif not scope.get("skipped_files"):
        scope_lines.append("No unreadable paths were encountered.")
    scope_lines.extend(["", "## Automatically excluded paths", ""])
    scope_lines.extend(f"- {item['path']} — {item['reason']}" for item in scope.get("auto_exclusions", []))
    scope_lines.extend(["", "## Suggested docagentignore patterns", "",
                        "Review these patterns before adding them. Use !path/to/file.js to include an automatically detected generated file.", ""])
    scope_lines.extend(scope.get("suggested_ignore_patterns", []))
    (directory / "Scope_Report.md").write_text("\n".join(scope_lines), encoding="utf-8")
    index = "\n".join(f"- [{DOCUMENT_PATHS[kind][2]}]({DOCUMENT_PATHS[kind][0]}/{DOCUMENT_PATHS[kind][1]}.md)" for kind in config.documents)
    (root / "README.md").write_text(
        f"# Application Documentation\n\n{metadata}\n\n## Reading order\n\n{index}\n\nThe main documents group application capabilities and contain proposed scenarios with explicit expected outcomes. Missing test design is disclosed. No execution or approval is implied.\n\nTechnical reviewers can follow [source citations](06-analysis/Evidence_Register.md), [API details](06-analysis/API_Reference.md), [implementation findings](06-analysis/Technical_Reference.md) and [limitations](06-analysis/Documentation_Gaps.md). Original implementation candidates and placeholder tests are preserved in Technical_Candidates.json.\n\nSource commit: {analysis['commit']}\nRequirements baseline: {state['baseline_hash']}\n",
        encoding="utf-8",
    )
    if scope.get("partial"):
        readme = root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nCoverage warning: some paths could not be inspected or the selected budget was reached. Results are partial. See [Scan coverage](06-analysis/Scope_Report.md).\n", encoding="utf-8")
    completed += 1
    report("Building documentation ZIP")
    manifest = [
        {"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size}
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
    (root / "manifest.json").write_text(
        json.dumps({"version": version, "generated": generated, "files": manifest}, indent=2),
        encoding="utf-8",
    )
    with zipfile.ZipFile(package_path(root), "x", zipfile.ZIP_DEFLATED) as archive:
        for file in root.rglob("*"):
            if file.is_file():
                archive.write(file, "repository-documentation/" + file.relative_to(root).as_posix())
    completed += 1
    report("Documentation package built; publishing artifacts")
    return manifest


def write_appendices(directory, analysis):
    evidence = {e["id"]: e for e in analysis["evidence"]}
    register = ["# Source Evidence Register", "", "Source citations are pinned to the inspected commit. Private repository links require access.", ""]
    for item in analysis["evidence"]:
        register.extend([f"## {item['id']}", "", evidence_text([item["id"]], evidence, analysis["repository"]), ""])
    (directory / "Evidence_Register.md").write_text("\n".join(register), encoding="utf-8")
    technical = ["# Implementation Reference", "", "This appendix retains extracted declarations and conditions. These are implementation findings rather than approved application requirements.", ""]
    api = ["# API Reference", "", "Declared routes are not proof of runtime payloads or access policy. Supporting examples are labelled explicitly.", ""]
    from docagent.reporting import supporting_path

    for finding in analysis["findings"]:
        technical.extend([f"## {finding['title']}", "", finding["detail"], "",
                          "Evidence: " + ", ".join(finding["evidence_ids"]), ""])
        if finding["kind"] == "api":
            path = evidence[finding["evidence_ids"][0]]["path"]
            api.extend([f"## {finding['title']}", "", f"Scope: {'Supporting example or test' if supporting_path(path) else 'Application'}.",
                        f"Declared handler: {finding['metadata'].get('handler', 'Unresolved')}.",
                        "Evidence: " + ", ".join(finding["evidence_ids"]), ""])
    (directory / "Technical_Reference.md").write_text("\n".join(technical), encoding="utf-8")
    (directory / "API_Reference.md").write_text("\n".join(api), encoding="utf-8")
