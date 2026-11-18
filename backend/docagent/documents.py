"""Seven consistent deliverables generated from a single versioned analysis snapshot."""

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from docagent.diagrams import export_graph, graph_sets
from docagent.security import redact_object

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


def build_sections(kind, analysis, state):
    evidence = {e["id"]: e for e in analysis["evidence"]}
    repo = analysis["repository"]
    sections = []

    def section(title, body):
        sections.append((title, body if isinstance(body, list) else [body]))

    def findings(title, kinds):
        body = []
        for f in analysis["findings"]:
            if f["kind"] in kinds:
                body.append(
                    f"{f['title']} [{f['confidence']}]\n{f['detail']}\n{evidence_text(f['evidence_ids'], evidence, repo)}"
                )
        section(
            title,
            body
            or [
                "No supporting evidence identified in the scanned scope. This does not prove the capability is absent."
            ],
        )

    if kind == "srs":
        section(
            "Application overview and scope",
            f"This as-is baseline documents {repo} at commit {analysis['commit']}. It records observed declarations and proposed requirements. Business purpose and stakeholder intent require review. Scope includes {analysis['stats']['scanned_files']} inspected files; exclusions and analysis budgets are recorded in the analysis summary.",
        )
        section(
            "Stakeholders and roles",
            "Project sponsor, business owner, engineering owner, QA lead, security reviewer and end-user roles: pending stakeholder identification. No names or authority are inferred from commit authors.",
        )
        findings("Repository described purpose", {"repository_description"})
        section(
            "Functional requirements",
            [
                f"{r['id']}  {r['title']}\nClassification: {r['confidence']}; source: {r['source']}; module: {r['module']}\n{r['statement']}\n{evidence_text(r['evidence_ids'], evidence, repo)}"
                for r in analysis["requirements"]
            ]
            or ["No functional requirement candidates could be extracted."],
        )
        findings("Business rules and workflows", {"business_rule", "function", "entrypoint"})
        findings("API and integration requirements", {"api", "integration"})
        findings("Authentication and authorization", {"security"})
        findings("Data management", {"data_model", "data_constraint", "data_access"})
        section(
            "Nonfunctional requirements",
            "Availability, throughput, latency, accessibility, recovery objectives and compliance targets are unverified. Configuration declarations are evidence of configuration only; they do not establish achieved service levels.",
        )
    elif kind == "requirements_signoff":
        section(
            "Requirements baseline",
            f"Baseline: {state['baseline_hash']}. Requirement candidates: {len(analysis['requirements'])}. Current status: {state['requirements_status']}. Approval requires an authorized reviewer acting on this exact baseline.",
        )
        section(
            "Review checklist",
            [
                "Confirm application scope and stakeholder roles.",
                "Review every requirement against its cited source and classify gaps.",
                "Confirm functional, API, data, security and nonfunctional requirements.",
                "Resolve assumptions or record explicit follow-up actions.",
                "Confirm requirement-to-test mappings and approve the baseline through the application.",
            ],
        )
        section(
            "Change management and approval criteria",
            "Requirement edits create a new version and invalidate previous approvals and results for that baseline. An authorized reviewer must acknowledge their decision. Comments are preserved in the audit trail.",
        )
        section("Stakeholder approval", approval_lines(state, "requirements"))
    elif kind == "test_cases":
        section(
            "Test strategy and scope",
            "These proposed positive, negative and boundary tests derive from requirement candidates. Refine fixtures and measurable expected outcomes during review. Generated cases are unexecuted until a reviewer records attested evidence. Existing repository test runs and manual UAT are recorded separately.",
        )
        section("Execution summary", [f"{key.title()}: {value}" for key, value in state["counts"].items()])
        result_map = {r["test_case_id"]: r for r in state["results"]}
        body = []
        for case in analysis["test_cases"]:
            result = result_map.get(case["id"])
            execution = (
                f"{result['status']} ({result['source']}, recorded by {result['reviewer']})\nActual: {result['actual']}\nEvidence: {result['evidence_reference']}\nSeverity: {result['severity']}"
                if result
                else "Unexecuted. Actual results: not available."
            )
            body.append(
                f"{case['id']}  {case['title']}\nRequirement: {case['requirement_id']}\nPreconditions: {' '.join(case['preconditions'])}\nSteps: {' '.join(f'{i + 1}. {step}' for i, step in enumerate(case['steps']))}\nExpected: {case['expected']}\nExecution: {execution}"
            )
        section("Detailed test cases", body or ["No test cases generated."])
        findings("Existing test inventory", {"test"})
        section(
            "Repository test execution",
            json.dumps(analysis.get("execution"), indent=2)
            if analysis.get("execution")
            else "Repository tests were not executed. Test-file presence is not a passing result.",
        )
        section(
            "UAT acceptance criteria",
            "Requirements approval must be current. Each generated case needs reliable recorded evidence. All cases must pass before the application permits final acceptance. Open failures or blocked and unexecuted cases prevent acceptance. Authorized humans make the final decision.",
        )
    elif kind == "uat_signoff":
        section(
            "Release and baseline",
            f"Application: {repo}. Source commit: {analysis['commit']}. Requirements baseline: {state['baseline_hash']}. Requirements approval: {state['requirements_status']}. UAT evidence baseline: {state['acceptance_hash']}.",
        )
        section(
            "UAT execution summary", [f"{key.title()}: {value}" for key, value in state["counts"].items()]
        )
        failures = [
            f"{r['test_case_id']}: {r['status']}; severity {r['severity']}; {r['actual']}"
            for r in state["results"]
            if r["status"] != "passed"
        ]
        section(
            "Open defects and limitations",
            failures
            or [
                "No defects recorded. This is not evidence of defect-free behavior; consult unexecuted case counts and analysis gaps."
            ],
        )
        section(
            "Requirement coverage and acceptance criteria",
            f"{len(analysis['requirements'])} requirements mapped to {len(analysis['test_cases'])} generated cases in the RTM. Generated mapping is design coverage, not execution coverage. Requirements approval and verified passing results for all cases are required.",
        )
        section(
            "Release readiness",
            "Eligible for authorized human acceptance review."
            if state["ready_for_acceptance"]
            else "Pending. Required baseline approval or passing execution evidence is incomplete.",
        )
        section("Stakeholder acceptance", approval_lines(state, "uat"))
    elif kind == "architecture":
        section(
            "Architecture overview",
            "The component view is reconstructed from source declarations and resolved local imports. It does not establish a live deployment topology. Disconnected nodes are retained when relationships are unsupported. Diagram views are bounded; the complete extracted edge list is in the JSON summary.",
        )
        findings("Components and entry points", {"entrypoint", "class", "api"})
        findings("Data stores and models", {"data_model", "data_constraint", "data_access"})
        findings("Authentication and external integrations", {"security", "integration"})
        findings("Containerization infrastructure and delivery", {"deployment"})
        section(
            "Component relationships",
            [f"{e['source']} imports {e['target']} at line {e['line']}." for e in analysis["edges"]]
            or [
                "No local dependency edges resolved. Dynamic imports, aliases and unsupported languages require manual review."
            ],
        )
        section(
            "Architecture diagram",
            "See Architecture_Diagram.svg, Architecture_Diagram.png, Architecture_Diagram.mmd and Architecture_Diagram.dot in this directory.",
        )
    elif kind == "data_flow":
        section(
            "Data flow scope",
            "Diagrams show only relationships supported by declarations. Caller identity, runtime request and response payloads, inter-service messages and persistence transactions need validation where no code evidence establishes them. Arrows are labelled with the specific relationship observed.",
        )
        section(
            "Level zero context",
            "See DFD_Level_0.svg. API callers are explicitly inferred actors. External hosts appear only when a literal HTTPS call was extracted.",
        )
        section(
            "Level one processes",
            "See DFD_Level_1.svg. Routes connect to their implementing modules. No database write or inter-service edge is invented from a dependency name.",
        )
        section(
            "Level two handler detail",
            "See DFD_Level_2.svg. Route-to-handler declarations are shown where parsed. If unsupported, the diagram explicitly records insufficient evidence.",
        )
        findings("API inputs and outputs", {"api"})
        findings(
            "Data models and integrations", {"data_model", "data_constraint", "data_access", "integration"}
        )
    elif kind == "technology":
        section(
            "Technology inventory",
            "Versions below are declared constraints unless the source specifies an exact version. A declared dependency does not establish runtime usage or installed version. Each item references its manifest or configuration evidence.",
        )
        section(
            "Programming languages",
            [
                f"{language}: {count} inspected files."
                for language, count in analysis["stats"]["languages"].items()
            ],
        )
        for category in sorted(
            {
                f["metadata"].get("category", "Other")
                for f in analysis["findings"]
                if f["kind"] == "technology"
            }
        ):
            section(
                category,
                [
                    f"{f['title']}\n{f['detail']}\nModule: {f['metadata'].get('module', '.')}.\n{evidence_text(f['evidence_ids'], evidence, repo)}"
                    for f in analysis["findings"]
                    if f["kind"] == "technology" and f["metadata"].get("category", "Other") == category
                ],
            )
    section("Assumptions dependencies and unresolved gaps", analysis["gaps"])
    return sections


def approval_lines(state, stage):
    records = [r for r in state["reviews"] if r["stage"] == stage and r["current"]]
    if not records:
        return [
            "Approval status: pending",
            "Stakeholder name and role: pending authorized identification",
            "Signature or authenticated decision: pending",
            "Approval date: pending",
            "Review comments: pending",
        ]
    return [
        f"Decision: {r['decision']}. Authenticated reviewer: {r['reviewer']}. Date: {r['created']} UTC.\nBaseline: {r['baseline_hash']}\nComment: {r['comment']}\nRecorded application decision; no handwritten signature is fabricated."
        for r in records
    ]


def markdown(title, metadata, sections):
    lines = [f"# {title}", "", metadata, ""]
    for heading, bodies in sections:
        lines.extend([f"## {heading}", ""])
        for body in bodies:
            lines.extend([body.replace("\n", "  \n"), ""])
    return "\n".join(lines)


def write_docx(path, title, metadata, sections):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.7)
    section.left_margin = section.right_margin = Inches(0.8)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(10 if name == "Normal" else 24 if name == "Title" else 15)
    document.styles["Normal"].paragraph_format.space_after = Pt(7)
    document.add_paragraph(title, "Title")
    document.add_paragraph(metadata)
    for heading, bodies in sections:
        document.add_heading(heading, level=1)
        for body in bodies:
            # Evidence URLs can be long; Word wraps them within normal paragraph width.
            p = document.add_paragraph(body)
            p.paragraph_format.widow_control = True
    section.footer.paragraphs[
        0
    ].text = "Repository documentation | Evidence-based draft and recorded human decisions"
    document.core_properties.title = title
    document.core_properties.author = "Repository Documentation Agent"
    document.save(path)


def write_pdf(path, title, metadata, sections):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "BodyWrap",
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=8,
            splitLongWords=True,
            wordWrap="LTR",
            alignment=TA_LEFT,
        )
    )
    styles["Title"].textColor = colors.black
    styles["Heading1"].textColor = colors.black

    def safe(text):
        # Standard PDF fonts use WinAnsi. Explicit replacement avoids invisible missing glyphs.
        return escape(text.encode("cp1252", errors="replace").decode("cp1252")).replace("\n", "<br/>")

    story = [
        Paragraph(safe(title), styles["Title"]),
        Paragraph(safe(metadata), styles["BodyWrap"]),
        Spacer(1, 12),
    ]
    for heading, bodies in sections:
        story.append(Paragraph(safe(heading), styles["Heading1"]))
        for body in bodies:
            story.append(Paragraph(safe(body), styles["BodyWrap"]))

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.7 * inch, 0.4 * inch, "Repository documentation")
        canvas.drawRightString(7.6 * inch, 0.4 * inch, str(doc.page))

    SimpleDocTemplate(
        str(path),
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=title,
    ).build(story, onFirstPage=footer, onLaterPages=footer)


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
    ]
    sheet.append(headers)
    requirements = {r["id"]: r for r in analysis["requirements"]}
    results = {r["test_case_id"]: r for r in state["results"]}
    for case in analysis["test_cases"]:
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
        ]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"  # Prevent spreadsheet formula injection from repository strings.
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="243449")
    widths = [24, 45, 38, 42, 24, 18, 20, 22, 45, 45]
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


def export_package(root: Path, analysis, config, state, version):
    root.mkdir(parents=True, exist_ok=False)
    analysis = redact_object(analysis)
    state = redact_object(state)
    generated = datetime.now(UTC).isoformat()
    metadata = f"Repository: {analysis['repository']}\nCommit: {analysis['commit']}\nDocument version: {version}\nGenerated: {generated}\nRequirements baseline: {state['baseline_hash']}"
    previews = {}
    for kind in config.documents:
        folder, filename, title = DOCUMENT_PATHS[kind]
        directory = root / folder
        directory.mkdir(exist_ok=True)
        sections = build_sections(kind, analysis, state)
        text = markdown(title, metadata, sections)
        previews[kind] = text
        # A text preview is always retained in addition to the selected export formats.
        (directory / f"{filename}.md").write_text(text, encoding="utf-8")
        if "docx" in config.formats:
            write_docx(directory / f"{filename}.docx", title, metadata, sections)
        if "pdf" in config.formats:
            write_pdf(directory / f"{filename}.pdf", title, metadata, sections)
    graphs = graph_sets(analysis)
    if "architecture" in config.documents:
        export_graph(root / "03-architecture", "Architecture_Diagram", graphs["Architecture_Diagram"])
    if "data_flow" in config.documents:
        for name in ("DFD_Level_0", "DFD_Level_1", "DFD_Level_2"):
            export_graph(root / "04-data-flow", name, graphs[name])
    if "test_cases" in config.documents or "uat_signoff" in config.documents:
        (root / "02-testing").mkdir(exist_ok=True)
        write_rtm(root / "02-testing" / "Requirements_Traceability_Matrix.xlsx", analysis, state)
    directory = root / "06-analysis"
    directory.mkdir(exist_ok=True)
    for filename, value in (
        ("Repository_Analysis_Summary.json", analysis),
        ("Evidence_Mapping.json", analysis["evidence"]),
        ("Workflow_and_Approvals.json", state),
    ):
        (directory / filename).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    (directory / "Documentation_Gaps.md").write_text(
        "# Documentation Gaps\n\n" + "\n".join(f"- {g}" for g in analysis["gaps"]), encoding="utf-8"
    )
    (root / "README.md").write_text(
        f"# Repository Documentation\n\n{metadata}\n\nGenerated requirements and tests require review. Approvals are recorded only from authenticated, authorized human decisions.\n\nSelected documents: {', '.join(config.documents)}.\n\nEvidence links are pinned to the analyzed commit. Markdown previews are always included. Private repository URLs require GitHub access.\n",
        encoding="utf-8",
    )
    manifest = [
        {"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size}
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
    (root / "manifest.json").write_text(
        json.dumps({"version": version, "generated": generated, "files": manifest}, indent=2),
        encoding="utf-8",
    )
    with zipfile.ZipFile(root.parent / f"v{version:04d}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file in root.rglob("*"):
            if file.is_file():
                archive.write(file, "repository-documentation/" + file.relative_to(root).as_posix())
    return manifest
