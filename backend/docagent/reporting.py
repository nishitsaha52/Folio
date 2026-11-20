"""Turn extracted declarations into a bounded, evidence-linked reader baseline.

This is deterministic: it never executes inspected source or invents successful
tests. Detailed implementation candidates remain available in the export appendix.
"""

import ast
import copy
import json
import re
import textwrap
from collections import defaultdict
from pathlib import PurePosixPath

from docagent.analysis import stable_id

REPORT_VERSION = "1"
SUPPORT_PARTS = {"test", "tests", "__tests__", "examples", "fixtures", "samples", "demo"}


def supporting_path(path):
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    return bool(set(parts) & SUPPORT_PARTS) or name.startswith("test_") or bool(
        re.search(r"\.(?:test|spec)\.[jt]sx?$", name)
    )


def words(value):
    return re.sub(r"\s+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", value).replace("_", " ")).strip()


def readable_name(value):
    """Explain common request/configuration names without exposing Python syntax."""
    value = value.replace("cfg.", "").replace("data.", "request ").replace("request.", "request ")
    value = value.replace("user.", "user ").replace("job.", "job ")
    text = words(value.replace(".", " "))
    text = text.replace("github", "GitHub").replace(" client id", " client ID")
    replacements = {"request acknowledged": "the required acknowledgement",
                    "request attested": "execution evidence confirmation",
                    "user owner": "the current account", "job owner": "the job owner",
                    "request baseline hash": "the supplied baseline identifier",
                    "job baseline hash": "the current baseline identifier", "expected hash": "the expected baseline identifier"}
    return replacements.get(text, text)


def parse_snippet(text):
    """Parse complete prefixes of bounded snippets; never treat missing lines as facts."""
    lines = textwrap.dedent(text).splitlines()
    for end in range(len(lines), 0, -1):
        try:
            return ast.parse("\n".join(lines[:end]))
        except (SyntaxError, ValueError, RecursionError):
            continue
    return ast.Module(body=[], type_ignores=[])


def application_purpose(analysis):
    descriptions = [f for f in analysis["findings"] if f["kind"] == "repository_description"]
    evidence = {e["id"]: e for e in analysis["evidence"]}
    descriptions.sort(key=lambda f: len(PurePosixPath(evidence[f["evidence_ids"][0]]["path"]).parts))
    for finding in descriptions:
        path = evidence[finding["evidence_ids"][0]]["path"]
        if supporting_path(path) and not analysis.get("report_scope", {}).get("includes_supporting"):
            continue
        for paragraph in re.split(r"\n\s*\n", finding["detail"]):
            paragraph = " ".join(paragraph.split())
            if paragraph and not paragraph.startswith(("#", "```", "[", "!", "<", "|")):
                return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph)[:900]
    return "This report describes the application capabilities supported by the inspected source. Its business purpose needs confirmation from the application owner."


def resource(route):
    parts = [p for p in route.split("/") if p and not p.startswith("{")]
    while parts and (parts[0] in {"api", "rest"} or re.fullmatch(r"v\d+", parts[0])):
        parts.pop(0)
    return parts[0] if parts else "application"


def operation_title(finding):
    meta = finding["metadata"]
    route, method = meta.get("route", "/"), meta.get("method", "GET")
    tail = [p for p in route.split("/") if p and not p.startswith("{")]
    noun = words(tail[-1]) if tail else "application"
    actions = {"GET": "View", "POST": "Create", "PUT": "Replace", "PATCH": "Update", "DELETE": "Remove"}
    special = {"download": "Download documents", "preview": "Preview a document", "logout": "Sign out",
               "pat": "Connect with a personal access token", "callback": "Handle a callback",
               "start": "Start a workflow", "health": "Check service health", "session": "View session settings"}
    if "/auth/github/" in route:
        special.update(start="Start GitHub sign in", callback="Complete GitHub sign in")
    contextual = {("POST", "jobs"): "Start a job", ("POST", "reviews"): "Record a review decision",
                  ("POST", "results"): "Record a test result", ("PATCH", "requirements"): "Edit a requirement",
                  ("POST", "collaborators"): "Grant collaborator access", ("DELETE", "collaborators"): "Revoke collaborator access",
                  ("GET", "files"): "List generated files", ("GET", "audit"): "View the audit history",
                  ("GET", "refs"): "List repository branches and tags", ("POST", "demo"): "Start the demonstration"}
    if (method, noun) in contextual:
        return contextual[(method, noun)]
    if method == "GET" and noun == "jobs":
        return "View a job" if "{" in route else "List jobs"
    return special.get(noun, f"{actions.get(method, method.title())} {noun}")


def condition_text(node):
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left = ast.unparse(node.left)
        if not re.fullmatch(r"[\w.]+", left):
            return None
        try:
            right = ast.literal_eval(node.comparators[0])
        except (ValueError, TypeError):
            value = node.comparators[0]
            if isinstance(value, (ast.Name, ast.Attribute)):
                right = readable_name(ast.unparse(value))
            elif isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
                right = f"the {value.value.id} value for {readable_name(ast.unparse(value.slice))}"
            else:
                return None
        operators = {ast.Eq: "equals", ast.NotEq: "does not equal", ast.Lt: "is less than",
                     ast.LtE: "is at most", ast.Gt: "is greater than", ast.GtE: "is at least",
                     ast.Is: "is", ast.IsNot: "is not", ast.In: "is present in", ast.NotIn: "is absent from"}
        op = operators.get(type(node.ops[0]))
        if op:
            if right is None and isinstance(node.ops[0], (ast.Is, ast.IsNot)):
                return f"the requested {readable_name(left)} {'does not exist' if isinstance(node.ops[0], ast.Is) else 'exists'}"
            return f"{readable_name(left)} {op} {right}"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, (ast.Name, ast.Attribute)):
        return f"{readable_name(ast.unparse(node.operand))} has not been supplied"
    return None


def observed_facts(records):
    rules, checks, descriptions, calls = [], [], [], set()
    for evidence in records:
        tree = parse_snippet(evidence["snippet"])
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    descriptions.append(doc.split("\n\n")[0])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            owner = parents.get(node)
            while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = parents.get(owner)
            if (isinstance(node, ast.Return) and node.value is not None and owner is not None
                    and not any(isinstance(part, ast.If) for part in ast.walk(owner))):
                try:
                    literal = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    literal = None
                if isinstance(literal, (str, int, bool, dict, list)):
                    try:
                        response = json.dumps(literal, ensure_ascii=False)
                    except (TypeError, ValueError):
                        continue
                    # A constant return is a reviewable response candidate, not proof
                    # that every request reaches this branch.
                    checks.append({"condition": "the documented success branch is reachable",
                                   "expected": f"The response value is {response}.",
                                   "evidence_id": evidence["id"], "category": "positive"})
                elif (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                      and node.value.func.attr == "copy" and isinstance(node.value.func.value, ast.Name)):
                    name = words(node.value.func.value.id)
                    checks.append({"condition": f"{name} contains a known test record",
                                   "expected": f"The returned mapping matches the seeded {name}; the source mapping remains unchanged.",
                                   "evidence_id": evidence["id"], "category": "positive"})
            if not isinstance(node, ast.If):
                continue
            # Only direct rejection branches. Nested branches have extra conditions.
            for child in node.body:
                if not isinstance(child, ast.Raise) or not isinstance(child.exc, ast.Call):
                    continue
                call = child.exc
                if ast.unparse(call.func).split(".")[-1] != "HTTPException":
                    continue
                args = dict(zip(("status_code", "detail"), call.args))
                args.update({kw.arg: kw.value for kw in call.keywords})
                try:
                    status = ast.literal_eval(args["status_code"])
                    detail = ast.literal_eval(args["detail"])
                except (ValueError, TypeError, KeyError):
                    continue
                if not isinstance(status, int) or not isinstance(detail, str):
                    continue
                condition = condition_text(node.test)
                text = f"When {condition}, the request is rejected with HTTP {status}: {detail}." if condition else (
                    f"A rejection branch returns HTTP {status}: {detail}. Its full preconditions need test design."
                )
                rules.append((text, evidence["id"]))
                if condition:
                    checks.append({"condition": condition, "expected": f"HTTP {status}; error detail: {detail}.",
                                   "evidence_id": evidence["id"]})
    return list(dict.fromkeys(descriptions)), list(dict.fromkeys(rules)), checks, calls


def refine_analysis(analysis):
    """Build a new review baseline, preserving every original candidate separately.

    Call only before a job's first baseline/signoff. Existing reviewed baselines
    must not be silently changed during preview, export or requirement editing.
    """
    if analysis.get("report_version") == REPORT_VERSION:
        return analysis
    result = copy.deepcopy(analysis)
    result["technical_candidates"] = {
        "requirements": result["requirements"], "test_cases": result["test_cases"],
    }
    evidence = {e["id"]: e for e in result["evidence"]}
    routes = [f for f in result["findings"] if f["kind"] == "api"]
    primary = [f for f in routes if not supporting_path(evidence[f["evidence_ids"][0]]["path"])]
    active_routes = primary or routes
    result["report_scope"] = {
        "includes_supporting": not bool(primary),
        "supporting_routes": len(routes) - len(active_routes),
        "description": "Application routes are grouped by resource. Tests, examples and implementation helpers are retained in the technical appendix.",
    }
    groups = defaultdict(list)
    for finding in active_routes:
        groups[resource(finding["metadata"].get("route", "/"))].append(finding)
    requirements, cases, features = [], [], []
    for key, members in sorted(groups.items()):
        eid_list, operations, all_rules, pending_checks = [], [], [], []
        for finding in members:
            meta = finding["metadata"]
            anchor = evidence[finding["evidence_ids"][0]]
            handler = meta.get("handler", "")
            related = [e for e in result["evidence"] if e["path"] == anchor["path"] and (
                e["id"] in finding["evidence_ids"] or handler and (e["symbol"] == handler or e["symbol"].startswith(handler + ":"))
            )]
            descriptions, rules, checks, calls = observed_facts(related)
            # Include directly named helper guards, without asserting a runtime call graph.
            helpers = [e for e in result["evidence"] if e["path"] == anchor["path"] and e["symbol"] in calls]
            _, helper_rules, helper_checks, _ = observed_facts(helpers)
            rules.extend(helper_rules)
            checks.extend(check for check in helper_checks if check.get("category") != "positive")
            related.extend(helpers)
            eid_list.extend(e["id"] for e in related)
            operation = {"title": operation_title(finding), "route": meta.get("route", finding["title"]),
                         "method": meta.get("method", ""), "description": descriptions[0] if descriptions else "",
                         "evidence_ids": finding["evidence_ids"], "path": anchor["path"]}
            operations.append(operation)
            all_rules.extend(text for text, _ in rules)
            for check in checks:
                pending_checks.append((operation, check))
        titles = {"auth": "Account connection", "repositories": "Repository selection",
                  "jobs": "Jobs and generated artifacts", "demo": "Demonstration workflow",
                  "health": "Service health", "session": "Session settings", "application": "Application entry point"}
        title = titles.get(key, words(key).capitalize() + " management")
        eid_list = list(dict.fromkeys(eid_list))
        rid = stable_id("REQ", "capability", key, *sorted({op["path"] for op in operations}))
        statement = f"The application provides {len(operations)} declared operations for {title.lower()}. The operation catalogue and source-supported rejection rules below define the observed scope."
        summaries = [r["statement"] for r in analysis["requirements"] if r["source"] == "llm"
                     and r["evidence_ids"] and set(r["evidence_ids"]) <= set(eid_list)]
        if summaries:
            statement = " ".join(dict.fromkeys(summaries))
        rules = list(dict.fromkeys(all_rules))
        requirements.append({"id": rid, "title": title, "statement": statement,
                             "confidence": "inferred", "evidence_ids": eid_list,
                             "module": ", ".join(sorted({op["path"] for op in operations})), "source": "static"})
        features.append({"requirement_id": rid, "title": title, "operations": operations, "rules": rules})
        for operation, check in pending_checks:
            cases.append({"id": stable_id("TC", rid, operation["method"], operation["route"], check["condition"], check["expected"]),
                          "requirement_id": rid, "title": f"{operation['title']} returns the expected response" if check.get("category") == "positive" else f"{operation['title']} when {check['condition']}",
                          "category": check.get("category", "negative"), "preconditions": [
                              "Use an isolated test deployment and a test session.",
                          ] + (["Replace path placeholders with identifiers selected for this test."] if "{" in operation["route"] else []),
                          "steps": ([] if check["condition"] == "the documented success branch is reachable" else [f"Arrange test data so that {check['condition']}."]) + [
                                        f"Send {operation['method']} {operation['route']}.",
                                        "Record the HTTP status and response body."],
                          "expected": check["expected"], "status": "unexecuted", "source": "static"})
    if not requirements:
        # Libraries and command-line repositories still get useful prose, but no
        # fabricated acceptance criteria from bare function names.
        by_module = defaultdict(list)
        for req in result["requirements"]:
            if not supporting_path(req["module"]):
                by_module[req["module"]].append(req)
        if not by_module:
            for req in result["requirements"]:
                by_module[req["module"]].append(req)
        for path, members in sorted(by_module.items()):
            ids = list(dict.fromkeys(eid for r in members for eid in r["evidence_ids"]))
            descriptions, _, _, _ = observed_facts([evidence[eid] for eid in ids if eid in evidence])
            ai = [r["statement"] for r in members if r["source"] in {"llm", "reviewer"}]
            text = " ".join(dict.fromkeys(ai or descriptions))
            if not text:
                text = f"This module declares {len(members)} public implementation candidates. Its user-facing behavior and acceptance criteria need review; declarations are listed in the technical reference."
            rid = stable_id("REQ", "module-capability", path)
            title = words(PurePosixPath(path).stem).capitalize()
            requirements.append({"id": rid, "title": title, "statement": text, "confidence": "inferred",
                                 "evidence_ids": ids, "module": path, "source": "static"})
            features.append({"requirement_id": rid, "title": title, "operations": [], "rules": []})
    # Preserve authored scenarios only when their citations map to the new feature.
    old_requirements = {r["id"]: r for r in analysis["requirements"]}
    for case in analysis["test_cases"]:
        if case.get("source") != "llm":
            continue
        old = old_requirements[case["requirement_id"]]
        ids = set(old["evidence_ids"])
        matches = [r for r in requirements if ids and ids <= set(r["evidence_ids"])]
        if len(matches) == 1:
            rid = matches[0]["id"]
            cases.append({**case, "id": stable_id("TC", rid, case["title"]), "requirement_id": rid})
    # Do not pad unsupported coverage with three identical templates per candidate.
    result["requirements"] = requirements
    result["test_cases"] = list({c["id"]: c for c in cases}.values())
    result["features"] = features
    result["report_version"] = REPORT_VERSION
    result["gaps"].append(
        "Only evidence-supported scenarios are included in the review baseline. Features without concrete cases require test design before acceptance. Original implementation candidates and placeholder tests are retained in Technical_Candidates.json."
    )
    return result


def balanced_evidence(analysis):
    """Round-robin source files before manifests/helpers can consume the AI budget."""
    evidence = analysis["evidence"]
    primary = [e for e in evidence if not supporting_path(e["path"])] or evidence
    buckets = defaultdict(list)
    for item in primary:
        buckets[item["path"]].append(item)
    api_ids = {eid for f in analysis["findings"] if f["kind"] == "api" for eid in f["evidence_ids"]}
    paths = sorted(buckets, key=lambda p: (not any(e["id"] in api_ids for e in buckets[p]),
                                           PurePosixPath(p).suffix not in {".py", ".ts", ".tsx", ".js"}, p))
    for path in paths:
        buckets[path].sort(key=lambda e: e["id"] not in api_ids)
    ordered = []
    for index in range(max((len(bucket) for bucket in buckets.values()), default=0)):
        for path in paths:
            if index < len(buckets[path]):
                ordered.append(buckets[path][index])
    return ordered
