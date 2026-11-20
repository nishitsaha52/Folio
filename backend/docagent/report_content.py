"""Reader-oriented sections shared by Markdown, Word and PDF exports."""

from collections import Counter
from pathlib import PurePosixPath

from docagent.reporting import application_purpose, supporting_path, words


def table(headers, rows):
    return {"table": {"headers": headers, "rows": [list(map(str, row)) for row in rows]}}


def evidence_refs(ids):
    return ", ".join(ids[:3]) + (f" and {len(ids) - 3} more" if len(ids) > 3 else "")


def component(path):
    """Labels group source dependencies, never assert a deployment topology."""
    parts = PurePosixPath(path).parts
    stem = PurePosixPath(path).stem
    if "migrations" in parts:
        return "Database migrations"
    if "frontend" in parts or "client" in parts:
        return "User interface"
    roles = {"api": "Application API", "routes": "Application API", "views": "Application API",
             "jobs": "Background processing", "queue": "Background processing", "worker": "Background processing",
             "analysis": "Repository analysis", "reporting": "Repository analysis", "imports": "Repository analysis",
             "llm": "AI synthesis", "documents": "Document exports", "report_content": "Document exports",
             "diagrams": "Document exports", "db": "Data persistence", "models": "Data persistence",
             "workflow": "Review workflow", "storage": "Artifact storage", "github": "GitHub integration",
             "security": "Security utilities", "config": "Application configuration"}
    return roles.get(stem, words(stem).capitalize())


def model_rows(analysis):
    ev = {e["id"]: e for e in analysis["evidence"]}
    rows = []
    for finding in analysis["findings"]:
        if finding["kind"] != "data_model":
            continue
        path = ev[finding["evidence_ids"][0]]["path"]
        if supporting_path(path) and not analysis.get("report_scope", {}).get("includes_supporting"):
            continue
        fields = finding["metadata"].get("fields", [])
        if not fields and finding["metadata"].get("bases"):
            continue
        rows.append((finding["title"], ", ".join(words(f) for f in fields) or "Fields require review",
                     evidence_refs(finding["evidence_ids"])))
    return rows


def approval_rows(state, stage):
    reviews = [r for r in state["reviews"] if r["stage"] == stage and r["current"]]
    return [(r["reviewer"], r["decision"], r["created"], r["comment"]) for r in reviews] or [
        ("Awaiting authorized reviewer", "Pending", "Not recorded", "No approval has been given")
    ]


def build_sections(kind, analysis, state):
    sections = []

    def section(title, *items):
        sections.append((title, list(items)))

    requirements = analysis["requirements"]
    features = {f["requirement_id"]: f for f in analysis.get("features", [])}
    cases = analysis["test_cases"]
    coverage = Counter(case["requirement_id"] for case in cases)
    missing = [r for r in requirements if not coverage[r["id"]]]
    results = {r["test_case_id"]: r for r in state["results"]}
    purpose = application_purpose(analysis)
    appendix = "Detailed source citations, implementation candidates and analysis limitations are in the 06-analysis folder. Evidence IDs in this document resolve through Evidence_Register.md."
    if kind == "srs":
        section("Purpose and scope", purpose,
                f"This draft groups the observed application interfaces into {len(requirements)} capabilities. It supports requirements review at commit {analysis['commit'][:12]}; business intent and runtime behavior still need owner confirmation.")
        section("Review summary", table(["Item", "Current position"], [
            ("Requirements approval", state["requirements_status"]),
            ("Capabilities", len(requirements)), ("Proposed scenarios", len(cases)),
            ("Capabilities needing test design", len(missing)),
            ("Inspected source files", analysis["stats"]["scanned_files"]),
        ]))
        for req in requirements:
            feature = features.get(req["id"], {})
            items = [f"Requirement {req['id']}. Classification: {req['confidence']}. {req['statement']}"]
            if feature.get("operations"):
                items = [f"Requirement {req['id']}. {req['statement']}", table(
                    ["Operation", "Description", "Evidence"],
                    [(op["title"], op["description"] or f"Declared interface: {op['method']} {op['route']}",
                      evidence_refs(op["evidence_ids"])) for op in feature["operations"]],
                )]
            rules = feature.get("rules", [])
            if rules:
                items.append({"list": [rule.replace("A rejection branch returns ", "The request can return ").replace(
                    " Its full preconditions need test design.", "") for rule in rules]})
                if any("full preconditions need test design" in rule for rule in rules):
                    items.append("Some rejection preconditions are incomplete in the inspected snippets. Confirm their fixtures and access context before using them as acceptance tests.")
            if not coverage[req["id"]]:
                items.append("Test design is required: the available evidence does not establish a concrete acceptance scenario for this capability.")
            section(req["title"], *items)
        models = model_rows(analysis)
        section("Data handled by the application", table(["Declared model", "Fields", "Evidence"], models) if models else "No data model was resolved in the inspected scope.")
        section("Decisions required before approval", {"list": [
            "Confirm the application owner, intended users and access privileges.",
            "Review inferred behavior against the pinned source and agree on measurable acceptance criteria.",
            "Complete missing test design and confirm supported environments.",
            "Set performance, availability, accessibility and recovery targets; source declarations do not establish achieved service levels.",
        ]}, appendix)
    elif kind == "test_cases":
        section("Test plan and current status",
                "These scenarios describe expected source behavior for review. None was executed by generating this document. Run them in an isolated test deployment and record actual outcomes separately.",
                table(["Measure", "Count"], [(k.capitalize(), v) for k, v in state["counts"].items()] + [("Capabilities needing test design", len(missing))]))
        for case in cases:
            result = results.get(case["id"])
            req = next(r for r in requirements if r["id"] == case["requirement_id"])
            section(case["title"], table(["Field", "Test specification"], [
                ("Test ID", case["id"]), ("Requirement", f"{req['title']} ({req['id']})"),
                ("Category", case["category"]), ("Preparation", "\n".join(case["preconditions"])),
                ("Actions", "\n".join(f"{i}. {s}" for i, s in enumerate(case["steps"], 1))),
                ("Expected outcome", case["expected"]),
                ("Recorded outcome", f"{result['status']}: {result['actual']}" if result else "Unexecuted. No actual result is recorded."),
            ]))
        if not cases:
            section("Test design required", "The inspected evidence does not establish concrete test inputs and outcomes. No placeholder scenarios have been promoted to executable test cases.")
        section("Coverage requiring design", table(["Capability", "Work required"], [(r["title"], "Specify fixtures, input values and measurable expected outcomes") for r in missing]) if missing else "Every capability has at least one proposed scenario. This does not establish complete positive, negative, boundary or security coverage.")
        section("Existing automated tests", f"The source scan identified {sum(f['kind'] == 'test' for f in analysis['findings'])} test declarations. Their implementation inventory is in the technical reference. Test-file presence does not establish a passing result.")
        section("Acceptance gate", "Acceptance requires current requirements approval, a concrete test design for every capability, reliable recorded passing evidence for every proposed case, and an authorized human decision.", appendix)
    elif kind in {"requirements_signoff", "uat_signoff"}:
        uat = kind == "uat_signoff"
        section("Decision to be recorded", f"Review {'acceptance evidence' if uat else 'the requirements'} for {analysis['repository']} at commit {analysis['commit'][:12]}. An authorized reviewer must record an explicit decision in the application. Changes create a new baseline and invalidate prior approval and test results.")
        section("Baseline and status", table(["Item", "Value"], [
            ("Requirements baseline", state["baseline_hash"]),
            ("Requirements approval", state["requirements_status"]),
            ("Capabilities in scope", len(requirements)),
            ("Capabilities needing test design", len(missing)),
        ] + ([("UAT baseline", state["acceptance_hash"]), ("UAT status", state["uat_status"]),
              ("Ready for acceptance", "Yes" if state["ready_for_acceptance"] else "No")] if uat else [])))
        section("Review checklist", {"list": [
            "Confirm scope, roles, access rules and unresolved decisions.",
            "Review the requirements and their source evidence.",
            "Complete missing test design and inspect recorded execution evidence.",
            "Record approval or requested changes against this exact baseline.",
        ]})
        section("Recorded decisions", table(["Reviewer", "Decision", "Date UTC", "Comment"], approval_rows(state, "uat" if uat else "requirements")))
    elif kind == "architecture":
        section("Architecture overview", purpose,
                "The component map groups inspected source modules by responsibility. Arrows represent declared code dependencies; they do not establish a live deployment topology.")
        groups = {}
        for item in analysis["inventory"]:
            if item["category"] == "source" and not supporting_path(item["path"]):
                groups.setdefault(component(item["path"]), []).append(item["path"])
        section("Source components",
                "Each row gives the source scope and one representative location. The complete file inventory remains in 06-analysis/Repository_Analysis_Summary.json.",
                table(["Component", "Source scope"], [(name, f"{len(paths)} source files. Example: {paths[0]}") for name, paths in sorted(groups.items())]))
        section("Component map", {"image": "Architecture_Diagram.png", "caption": "Source dependency map with implementation helpers grouped by responsibility"})
        models = model_rows(analysis)
        section("Data structures", table(["Model", "Declared fields", "Evidence"], models) if models else "No supported data model was resolved.")
        section("Deployment questions", "Confirm deployed services, database and object-store endpoints, worker topology, trust boundaries and capacity with the deployment owner. Dependency manifests alone do not prove installed or active infrastructure.", appendix)
    elif kind == "data_flow":
        section("Interfaces and data flow scope", "This document explains the interfaces visible in source and the information still needed for a runtime data-flow model. Declared route handlers and imports do not prove payload movement between services.")
        section("Application context", {"image": "DFD_Level_0.png", "caption": "Declared application interfaces and literal external HTTPS calls"})
        section("Capability interfaces", {"image": "DFD_Level_1.png", "caption": "Interfaces grouped by application capability"})
        section("Handler detail", {"image": "DFD_Level_2.png", "caption": "Representative source handlers with full details in API_Reference.md"})
        section("Information needed to complete the model", table(["Flow question", "Evidence needed"], [
            ("Who sends the request", "Confirmed user roles, client applications and effective authorization"),
            ("What is received and returned", "Reviewed request and response schemas, validation rules and examples"),
            ("What is persisted", "Confirmed storage operations, transaction boundaries and retention settings"),
            ("What crosses a trust boundary", "Verified integrations, credentials handling and deployment configuration"),
        ]), appendix)
    elif kind == "technology":
        section("Technology overview", "This inventory lists declared dependencies and their intended purpose. Version ranges are manifest constraints; deployed versions and actual runtime use require verification.")
        section("Languages", table(["Language", "Inspected files"], sorted(analysis["stats"]["languages"].items())))
        categories = {}
        for f in analysis["findings"]:
            if f["kind"] == "technology":
                meta = f["metadata"]
                categories.setdefault(meta.get("category", "Other"), []).append((
                    f["title"], meta.get("version", "Unspecified"), meta.get("purpose", f["detail"]), evidence_refs(f["evidence_ids"]),
                ))
        for name, rows in sorted(categories.items()):
            section(name, table(["Technology", "Declared version", "Purpose", "Evidence"], rows))
        section("Verification needed", "Confirm installed versions, ownership, security maintenance and actual runtime configuration before relying on this inventory for release decisions.", appendix)
    skipped = analysis.get("scope", {}).get("skipped_files", [])
    if skipped and sections:
        sections[0][1].insert(0, f"Coverage warning: {len(skipped)} paths could not be inspected. These results are partial. Review 06-analysis/Scope_Report.md before making a signoff decision.")
    if analysis.get("scope", {}).get("budget_reached") and sections:
        sections[0][1].insert(0, "Coverage warning: the selected analysis budget was reached. Some source files were not inspected. Review Scan coverage before signoff.")
    return sections
