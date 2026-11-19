"""Bounded static analysis. Repository code is never imported or executed."""

import ast
import hashlib
import json
import re
import tomllib
from collections import Counter
from pathlib import Path

import pathspec
from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement as PackageRequirement

from docagent.config import settings
from docagent.db import ScanCache, digest, save_cache
from docagent.imports import import_edges
from docagent.schemas import Confidence, Evidence, Finding, Requirement, TestCase
from docagent.security import redact, redact_object, secret_path

ANALYZER_VERSION = "1.2"
LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".sh": "Shell",
    ".tf": "Terraform",
}
IGNORED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
    "dist",
    "build",
    ".next",
    ".data",
    "coverage",
    "target",
    ".idea",
}
TEXT_EXTENSIONS = set(LANGUAGES) | {
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".properties",
    ".gradle",
    ".proto",
    ".graphql",
    ".prisma",
}
KNOWN_TECH = {
    "react": ("Frontend", "User interface"),
    "next": ("Frontend", "Web application framework"),
    "vue": ("Frontend", "User interface"),
    "@angular/core": ("Frontend", "Web application framework"),
    "fastapi": ("Backend", "HTTP API framework"),
    "django": ("Backend", "Web application framework"),
    "flask": ("Backend", "HTTP application framework"),
    "express": ("Backend", "HTTP server framework"),
    "spring-boot": ("Backend", "Java application framework"),
    "sqlalchemy": ("Databases", "SQL persistence toolkit"),
    "psycopg": ("Databases", "PostgreSQL driver"),
    "psycopg2-binary": ("Databases", "PostgreSQL driver"),
    "pg": ("Databases", "PostgreSQL driver"),
    "pymongo": ("Databases", "MongoDB driver"),
    "mongoose": ("Databases", "MongoDB object modeling"),
    "redis": ("Databases", "Redis client"),
    "mysqlclient": ("Databases", "MySQL driver"),
    "pytest": ("Testing", "Python testing"),
    "jest": ("Testing", "JavaScript testing"),
    "vitest": ("Testing", "JavaScript testing"),
    "playwright": ("Testing", "Browser testing"),
    "selenium": ("Testing", "Browser testing"),
    "@playwright/test": ("Testing", "Browser testing"),
    "pyjwt": ("Security", "JWT handling"),
    "bcrypt": ("Security", "Password hashing"),
    "cryptography": ("Security", "Cryptographic primitives"),
    "passport": ("Security", "Authentication middleware"),
    "openai": ("AI and ML", "OpenAI API client"),
    "anthropic": ("AI and ML", "Claude API client"),
    "google-genai": ("AI and ML", "Gemini API client"),
    "torch": ("AI and ML", "Machine learning"),
    "tensorflow": ("AI and ML", "Machine learning"),
    "pgvector": ("AI and ML", "Vector storage"),
    "boto3": ("Infrastructure", "AWS API client"),
    "google-cloud-storage": ("Infrastructure", "Google Cloud storage client"),
    "azure-identity": ("Infrastructure", "Azure authentication"),
    "prometheus-client": ("Monitoring", "Metrics instrumentation"),
    "sentry-sdk": ("Monitoring", "Error monitoring"),
    "celery": ("Background processing", "Distributed tasks"),
    "temporalio": ("Background processing", "Workflow orchestration"),
    "grpcio": ("Communication", "gRPC transport"),
    "graphql": ("Communication", "GraphQL schema and queries"),
    "websockets": ("Communication", "WebSocket transport"),
}


def stable_id(prefix, *values):
    return prefix + "-" + hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()[:12].upper()


def classify(path: str):
    p = Path(path)
    if (
        p.name.startswith("test_")
        or p.name.endswith((
            "_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
            ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx", "_test.go",
        ))
        or any(x in {"tests", "test", "__tests__"} for x in p.parts)
    ):
        return "test"
    if (
        ".github/workflows" in path
        or p.name in {"Dockerfile", "Jenkinsfile", "docker-compose.yml", "compose.yaml", "compose.yml"}
        or p.suffix == ".tf"
        or "k8s" in p.parts
        or "helm" in p.parts
    ):
        return "deployment"
    if p.suffix in LANGUAGES:
        return "source"
    if p.suffix == ".md" or p.name.lower() in {"readme", "license", "notice", "changelog", "contributing"}:
        return "documentation"
    return "configuration"


class Collector:
    def __init__(self, path, text):
        self.path = path
        self.text = text
        self.lines = text.splitlines()
        self.findings = []
        self.evidence = []
        self.imports = []
        self.gaps = []

    def add(self, kind, title, detail, line=1, end=None, symbol="", confidence="verified", metadata=None):
        line = max(1, min(line, max(1, len(self.lines))))
        end = min(end or line, line + 14, max(1, len(self.lines)))
        snippet = redact("\n".join(self.lines[line - 1 : end]))[:2400]
        eid = stable_id("EV", self.path, line, symbol, snippet)
        if not any(e["id"] == eid for e in self.evidence):
            self.evidence.append(
                Evidence(
                    id=eid, path=self.path, start_line=line, end_line=end, symbol=symbol, snippet=snippet
                ).model_dump()
            )
        identity = symbol or title
        fid = stable_id("F", self.path, kind, identity)
        # Duplicate decorators/overloads remain a single finding with all evidence references.
        existing = next((f for f in self.findings if f["id"] == fid), None)
        if existing:
            if eid not in existing["evidence_ids"]:
                existing["evidence_ids"].append(eid)
            return
        self.findings.append(
            Finding(
                id=fid,
                kind=kind,
                title=redact(title),
                detail=redact(detail),
                confidence=confidence,
                evidence_ids=[eid],
                metadata=metadata or {},
            ).model_dump(mode="json")
        )

    def dependency(self, name, version, line=1):
        category, purpose = KNOWN_TECH.get(
            name.lower(), ("Libraries", "Declared dependency; usage requires module inspection")
        )
        self.add(
            "technology",
            name,
            f"{purpose}. Declared version or constraint: {version or 'not specified'}.",
            line,
            symbol=name,
            metadata={
                "name": name,
                "version": version or "not specified",
                "category": category,
                "purpose": purpose,
                "module": str(Path(self.path).parent),
            },
        )

    def payload(self):
        return redact_object(
            {"findings": self.findings, "evidence": self.evidence, "imports": self.imports, "gaps": self.gaps}
        )


def python_analysis(c: Collector):
    try:
        tree = ast.parse(c.text)
    except (SyntaxError, ValueError, RecursionError):
        c.gaps.append(f"Python syntax could not be parsed: {c.path}")
        return
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def qualified(node):
        names = [node.name]
        parent = parents.get(node)
        while parent:
            if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.insert(0, parent.name)
            parent = parents.get(parent)
        return ".".join(names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                c.imports.append({"module": alias.name, "line": node.lineno, "level": 0})
        elif isinstance(node, ast.ImportFrom):
            c.imports.append(
                {
                    "module": node.module or "",
                    "line": node.lineno,
                    "level": node.level,
                    "names": [a.name for a in node.names],
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol = qualified(node)
            is_test = classify(c.path) == "test"
            args = [a.arg for a in node.args.args]
            returns = ast.unparse(node.returns) if node.returns else "unspecified"
            doc = ast.get_docstring(node) or "No function description is provided."
            c.add(
                "test" if is_test else "function",
                symbol,
                f"{'Test' if is_test else 'Function'} declaration. Parameters: {', '.join(args) or 'none'}. Return annotation: {returns}. {doc[:600]}",
                node.lineno,
                node.end_lineno,
                symbol,
                metadata={"parameters": args, "returns": returns},
            )
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                    method = deco.func.attr.lower()
                    if (
                        method
                        in {"get", "post", "put", "patch", "delete", "options", "head", "route", "websocket"}
                        and deco.args
                        and isinstance(deco.args[0], ast.Constant)
                        and isinstance(deco.args[0].value, str)
                    ):
                        route = deco.args[0].value
                        methods = [method.upper()]
                        if method == "route":
                            methods = ["GET"]
                            for kw in deco.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                                    methods = [
                                        v.value
                                        for v in kw.value.elts
                                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                                    ]
                        for verb in methods:
                            c.add(
                                "api",
                                f"{verb} {route}",
                                f"Decorator declares {verb} {route}, handled by {symbol}. Router mount prefixes and runtime middleware require verification.",
                                deco.lineno,
                                node.end_lineno,
                                f"{symbol}:{verb}:{route}",
                                metadata={
                                    "method": verb,
                                    "route": route,
                                    "handler": symbol,
                                    "parameters": args,
                                    "returns": returns,
                                },
                            )
        elif isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            fields = [
                n.target.id
                for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            ]
            model = any(re.search(r"\b(Base|Model|Document|BaseModel|DeclarativeBase)\b", b) for b in bases)
            c.add(
                "data_model" if model else "class",
                qualified(node),
                f"Class bases: {', '.join(bases) or 'none'}. Annotated fields: {', '.join(fields) or 'none'}. Persistence cannot be concluded from class naming alone.",
                node.lineno,
                node.end_lineno,
                qualified(node),
                metadata={"bases": bases, "fields": fields},
            )
        elif isinstance(node, (ast.If, ast.Assert)) and classify(c.path) != "test":
            expression = ast.unparse(node.test)[:500]
            owner = parents.get(node)
            while owner and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = parents.get(owner)
            if owner:
                c.add(
                    "business_rule",
                    f"Condition in {qualified(owner)}",
                    f"Code evaluates: {expression}. Business intent and supported input boundaries require review.",
                    node.lineno,
                    node.end_lineno,
                    f"{qualified(owner)}:{expression}",
                    confidence="inferred",
                )
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name.split(".")[-1] in {"Depends", "Security"} and node.args:
                dependency = ast.unparse(node.args[0])
                c.add(
                    "security",
                    f"Dependency {dependency}",
                    f"Dependency injection references {dependency}. Review this dependency to establish authentication and permissions.",
                    node.lineno,
                    symbol=dependency,
                    confidence="inferred",
                )
            if name.split(".")[-1] in {"Field", "Column", "mapped_column", "relationship", "ForeignKey"}:
                declaration = ast.unparse(node)[:700]
                c.add(
                    "data_constraint",
                    name,
                    f"Schema or validation declaration: {declaration}",
                    node.lineno,
                    node.end_lineno,
                    declaration,
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "execute",
                "query",
                "commit",
                "flush",
                "save",
                "insert_one",
                "find_one",
                "bulk_write",
            }:
                c.add(
                    "data_access",
                    name,
                    f"Call to {name} may participate in data access. Receiver type, transaction boundaries and runtime store require verification.",
                    node.lineno,
                    node.end_lineno,
                    f"{name}:{node.lineno}",
                    confidence="inferred",
                )
            if any(
                word in name.lower()
                for word in (
                    "authenticate",
                    "authorize",
                    "require_user",
                    "require_role",
                    "hashpw",
                    "jwt.decode",
                    "verify_password",
                )
            ):
                c.add(
                    "security",
                    name,
                    f"Security-related call to {name}; the effective authorization policy requires review.",
                    node.lineno,
                    symbol=name,
                    confidence="inferred",
                )
            if (
                re.search(r"(?:requests|httpx|client|session)\.(get|post|put|delete|patch|request)$", name)
                and node.args
            ):
                if (
                    isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value.startswith("https://")
                ):
                    from urllib.parse import urlparse

                    host = urlparse(node.args[0].value).hostname
                    c.add(
                        "integration",
                        f"HTTPS call to {host}",
                        f"{name} is called with an HTTPS URL on {host}.",
                        node.lineno,
                        symbol=f"{name}:{host}",
                        metadata={"host": host},
                    )


    # Preserve lexical ownership so requirements can combine a handler or model
    # with its guards and constraints instead of creating a review item per AST node.
    scopes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    evidence = {item["id"]: item for item in c.evidence}
    for finding in c.findings:
        line = evidence[finding["evidence_ids"][0]]["start_line"]
        enclosing = [node for node in scopes if node.lineno <= line <= node.end_lineno]
        if enclosing:
            scope = min(enclosing, key=lambda node: node.end_lineno - node.lineno)
            finding["metadata"]["scope"] = qualified(scope)
        classes = [node for node in enclosing if isinstance(node, ast.ClassDef)]
        if classes:
            finding["metadata"]["class_scope"] = qualified(
                min(classes, key=lambda node: node.end_lineno - node.lineno)
            )


def tree_analysis(c: Collector, extension):
    """Syntax tree extraction for JavaScript, TypeScript, Java and Go."""
    try:
        from tree_sitter import Language, Parser

        if extension in {".js", ".jsx"}:
            import tree_sitter_javascript as grammar

            language = grammar.language()
        elif extension in {".ts", ".tsx"}:
            import tree_sitter_typescript as grammar

            language = grammar.language_tsx() if extension == ".tsx" else grammar.language_typescript()
        elif extension == ".java":
            import tree_sitter_java as grammar

            language = grammar.language()
        else:
            import tree_sitter_go as grammar

            language = grammar.language()
        tree = Parser(Language(language)).parse(c.text.encode())
        if tree.root_node.has_error:
            c.gaps.append(f"Partial syntax parse contains errors: {c.path}")
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(reversed(node.children))
            if node.type in {
                "function_declaration",
                "method_definition",
                "method_declaration",
                "function_definition",
                "class_declaration",
                "interface_declaration",
                "type_declaration",
            }:
                name = node.child_by_field_name("name")
                if name:
                    value = name.text.decode()
                    kind = (
                        "class"
                        if node.type in {"class_declaration", "interface_declaration", "type_declaration"}
                        else "function"
                    )
                    if classify(c.path) == "test":
                        kind = "test"
                    c.add(
                        kind,
                        value,
                        f"{node.type.replace('_', ' ')} found by syntax parser.",
                        node.start_point.row + 1,
                        node.end_point.row + 1,
                        value,
                    )
    except (ImportError, TypeError, ValueError):
        c.gaps.append(
            f"Tree-sitter parser unavailable for {c.path}; only declared dependencies and heuristics inspected."
        )
    for m in re.finditer(r"(?:import\s+.*?from\s*|require\s*\(\s*|import\s*)['\"]([^'\"]+)['\"]", c.text):
        c.imports.append({"module": m.group(1), "line": c.text.count("\n", 0, m.start()) + 1, "level": 0})
    for m in re.finditer(
        r"\b(?:app|router|server)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", c.text
    ):
        verb, route = m.group(1).upper(), m.group(2)
        c.add(
            "api",
            f"{verb} {route}",
            f"Route-like call declares {verb} {route}; framework binding requires verification.",
            c.text.count("\n", 0, m.start()) + 1,
            symbol=f"{verb}:{route}",
            confidence="inferred",
            metadata={"method": verb, "route": route},
        )


def dependencies(c: Collector):
    name = Path(c.path).name.lower()
    try:
        if name == "package.json":
            data = json.loads(c.text)
            for group in ("dependencies", "devDependencies", "peerDependencies"):
                for package, version in data.get(group, {}).items():
                    line = next((i + 1 for i, v in enumerate(c.lines) if f'"{package}"' in v), 1)
                    c.dependency(package, str(version), line)
            for script, command in data.get("scripts", {}).items():
                c.add("entrypoint", f"npm run {script}", f"Declared script: {command}", symbol=script)
        elif name == "pyproject.toml":
            data = tomllib.loads(c.text)
            values = list(data.get("project", {}).get("dependencies", []))
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                values.extend(group)
            for value in values:
                try:
                    package = PackageRequirement(value)
                    line = next(
                        (i + 1 for i, v in enumerate(c.lines) if package.name.lower() in v.lower()), 1
                    )
                    c.dependency(package.name, str(package.specifier), line)
                except InvalidRequirement:
                    pass
            for package, version in data.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
                c.dependency(package, str(version))
            for entry, target in data.get("project", {}).get("scripts", {}).items():
                c.add("entrypoint", entry, f"Console entry point: {target}", symbol=entry)
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line, value in enumerate(c.lines, 1):
                try:
                    package = PackageRequirement(value.split(" #")[0])
                    c.dependency(package.name, str(package.specifier), line)
                except InvalidRequirement:
                    continue
        elif name == "cargo.toml":
            data = tomllib.loads(c.text)
            for group in ("dependencies", "dev-dependencies", "build-dependencies"):
                for package, version in data.get(group, {}).items():
                    c.dependency(package, str(version))
        elif name == "go.mod":
            for line, text in enumerate(c.lines, 1):
                m = re.match(r"\s*(?:require\s+)?([\w./-]+)\s+(v[\w.+-]+)", text)
                if m:
                    c.dependency(m.group(1), m.group(2), line)
        elif name == "pom.xml":
            from defusedxml.ElementTree import fromstring

            root = fromstring(c.text)
            ns = {"m": "http://maven.apache.org/POM/4.0.0"}
            for dep in root.findall(".//m:dependency", ns):
                artifact = dep.findtext("m:artifactId", namespaces=ns)
                if artifact:
                    c.dependency(
                        artifact, dep.findtext("m:version", default="managed externally", namespaces=ns)
                    )
    except (ValueError, TypeError, AttributeError):
        c.gaps.append(f"Dependency manifest could not be fully parsed: {c.path}")


def analyze_file(path, text):
    c = Collector(path, text)
    p = Path(path)
    if p.name.lower() in {"readme", "readme.md", "readme.txt", "readme.rst"}:
        c.add(
            "repository_description", "Repository stated purpose", text[:1200], 1, 15, confidence="inferred"
        )
    if p.suffix == ".py":
        python_analysis(c)
    elif p.suffix in {".js", ".jsx", ".ts", ".tsx", ".java", ".go"}:
        tree_analysis(c, p.suffix)
    elif p.suffix in LANGUAGES and p.suffix not in {".sql", ".html", ".css"}:
        c.gaps.append(f"No semantic parser for {LANGUAGES[p.suffix]}: {path}")
    dependencies(c)
    if classify(path) == "deployment":
        c.add(
            "deployment",
            path,
            "Deployment configuration exists; deployment execution and environment are not verified.",
            1,
            15,
        )
        if p.name == "Dockerfile":
            for i, line in enumerate(c.lines, 1):
                if re.match(r"(?i)^(FROM|EXPOSE|ENTRYPOINT|CMD)\s", line):
                    c.add(
                        "deployment", line[:180], f"Container declaration: {line[:500]}", i, symbol=line[:180]
                    )
    if p.suffix == ".sql":
        for m in re.finditer(r"(?i)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`]+)", text):
            line = text.count("\n", 0, m.start()) + 1
            c.add(
                "data_model",
                m.group(1),
                "SQL table declaration. Review migrations for lifecycle and relationships.",
                line,
                line + 10,
                m.group(1),
            )
    if p.suffix in {".yaml", ".yml", ".json", ".toml", ".tf"}:
        for name, pattern, category in [
            ("Kubernetes", r"(?m)^apiVersion:\s*(?:apps/|v1)", "Containerization"),
            ("GitHub Actions", r"(?m)^jobs:\s*$", "CI/CD"),
            ("Terraform", r'\bprovider\s+"[a-z]+"', "Infrastructure"),
        ]:
            if re.search(pattern, text) and (name != "GitHub Actions" or ".github/workflows" in path):
                c.add(
                    "technology",
                    name,
                    f"{name} configuration detected.",
                    metadata={
                        "name": name,
                        "version": "not specified",
                        "category": category,
                        "purpose": "Infrastructure configuration",
                        "module": str(p.parent),
                    },
                )
    if p.name == "Dockerfile":
        c.add(
            "technology",
            "Docker",
            "Container build configuration exists.",
            metadata={
                "name": "Docker",
                "version": "not specified",
                "category": "Containerization",
                "purpose": "Container image build",
                "module": str(p.parent),
            },
        )
    return c.payload()


def scan_repository(root: Path, commit: str, depth="standard", db=None, cache_scope="local", progress=None):
    cfg = settings()
    root = root.resolve()
    limit = {"basic": 400, "standard": 3000, "comprehensive": 15000}[depth]
    byte_limit = {"basic": 4_000_000, "standard": 20_000_000, "comprehensive": 80_000_000}[depth]
    rules = []
    for ignore in (".gitignore", ".docagentignore"):
        path = root / ignore
        if path.is_file() and not path.is_symlink() and path.stat().st_size < 100_000:
            rules.extend(path.read_text(errors="replace").splitlines())
    spec = pathspec.PathSpec.from_lines("gitwildmatch", rules)
    inventory, findings, evidence, imports, gaps = [], [], [], {}, []
    reused, scanned, total_bytes, excluded = 0, 0, 0, 0
    # top-down traversal prunes dependencies instead of enumerating their entire contents.
    import os

    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in IGNORED
            and not (Path(directory) / d).is_symlink()
            and not secret_path((Path(directory) / d).relative_to(root).as_posix())
            and not spec.match_file((Path(directory) / d).relative_to(root).as_posix() + "/")
        )
        for filename in sorted(files):
            file = Path(directory) / filename
            relative = file.relative_to(root).as_posix()
            if file.is_symlink() or secret_path(relative) or spec.match_file(relative):
                excluded += 1
                continue
            if file.suffix.lower() not in TEXT_EXTENSIONS and filename.lower() not in {
                "dockerfile",
                "jenkinsfile",
                "go.mod",
                "gemfile",
                "readme",
                "license",
                "notice",
                "changelog",
                "contributing",
                ".gitignore",
                ".dockerignore",
                "makefile",
                "procfile",
                ".editorconfig",
            }:
                excluded += 1
                continue
            size = file.stat().st_size
            if size > cfg.max_file_bytes:
                gaps.append(f"File exceeds analysis size limit: {relative}")
                continue
            if scanned >= limit or total_bytes + size > byte_limit:
                gaps.append(
                    f"{depth.title()} analysis budget reached. Some files were not inspected; use a deeper scan or narrow .docagentignore."
                )
                dirs[:] = []
                break
            raw = file.read_bytes()
            if b"\0" in raw:
                excluded += 1
                continue
            checksum = hashlib.sha256(raw).hexdigest()
            text = raw.decode("utf-8", errors="replace")
            scanned += 1
            total_bytes += size
            inventory.append(
                {
                    "path": relative,
                    "sha256": checksum,
                    "bytes": size,
                    "language": LANGUAGES.get(file.suffix, "Configuration / text"),
                    "category": classify(relative),
                }
            )
            key = digest([ANALYZER_VERSION, cache_scope, relative, checksum])
            cached = db.get(ScanCache, key) if db is not None else None
            if cached:
                payload = cached.payload
                reused += 1
            else:
                payload = analyze_file(relative, text)
                if db is not None:
                    save_cache(db, key, payload)
            findings.extend(payload["findings"])
            evidence.extend([{**e, "commit": commit} for e in payload["evidence"]])
            imports[relative] = payload["imports"]
            gaps.extend(payload["gaps"])
            if progress and scanned % 100 == 0:
                progress(scanned)
    edges = import_edges(root, inventory, imports)
    requirements = candidate_requirements(findings, evidence)
    if not any(f["kind"] == "test" for f in findings):
        gaps.append("No test declarations were identified in the scanned scope.")
    gaps.extend(
        [
            "Static requirements group declarations, guards and constraints by public callable or model. Internal helpers and test code remain in findings and evidence rather than separate acceptance items.",
            "Static analysis does not establish business intent, runtime correctness, performance, availability or regulatory compliance.",
            "User roles, stakeholders, service-level targets and acceptance thresholds require authorized review.",
            "Import relationships describe code dependencies, not proven runtime data movement. Conditional calls and dynamic routing may be incomplete.",
            "Existing test files are not execution evidence. Coverage percentages require a trusted coverage report.",
            "Submodules and Git LFS objects are not recursively retrieved.",
        ]
    )
    return {
        "schema_version": 1,
        "analyzer_version": ANALYZER_VERSION,
        "commit": commit,
        "inventory": inventory,
        "findings": findings,
        "evidence": evidence,
        "requirements": requirements,
        "test_cases": generate_tests(requirements),
        "edges": edges,
        "gaps": list(dict.fromkeys(gaps)),
        "stats": {
            "scanned_files": scanned,
            "reused_files": reused,
            "excluded_files": excluded,
            "scanned_bytes": total_bytes,
            "languages": dict(Counter(f["language"] for f in inventory)),
        },
        "usage": [],
        "execution": None,
    }


def candidate_requirements(findings, evidence):
    evidence_by_id = {item["id"]: item for item in evidence}
    relevant = {"api", "function", "business_rule", "security", "data_model", "data_constraint", "integration"}
    routes = {
        (evidence_by_id[item["evidence_ids"][0]]["path"], item["metadata"].get("handler"))
        for item in findings if item["kind"] == "api"
    }
    groups = {}
    for finding in findings:
        if finding["kind"] not in relevant:
            continue
        ev = evidence_by_id[finding["evidence_ids"][0]]
        path = ev["path"]
        if classify(path) == "test":
            continue
        metadata = finding["metadata"]
        scope = metadata.get("handler") or metadata.get("scope")
        if not scope and finding["kind"] in {"function", "data_model"}:
            scope = ev["symbol"] or finding["title"]
        is_route = (path, scope) in routes
        if metadata.get("class_scope") and not is_route:
            scope = metadata["class_scope"]
        if scope and not is_route and any(part.startswith("_") for part in scope.split(".")):
            continue
        groups.setdefault((path, scope or "module"), []).append(finding)

    requirements = []
    for (path, scope), members in groups.items():
        anchor = min(members, key=lambda item: {"api": 0, "data_model": 1, "function": 2}.get(item["kind"], 3))
        details = [anchor["detail"]]
        for item in members:
            if item is not anchor and item["kind"] != "function" and item["detail"] not in details:
                details.append(item["detail"])
        requirements.append(
            Requirement(
                id=stable_id("REQ", path, scope),
                title=anchor["title"] if scope != "module" else f"Implementation rules in {path}",
                statement="\n".join(details),
                confidence=Confidence.inferred,
                evidence_ids=list(dict.fromkeys(eid for item in members for eid in item["evidence_ids"])),
                module=path,
            ).model_dump(mode="json")
        )
    return requirements


def generate_tests(requirements):
    cases = []
    for requirement in requirements:
        for category, action, expected in [
            (
                "positive",
                "Prepare a valid fixture after reviewing the cited implementation. Invoke the documented function or API and record the response and state changes.",
                "Observed behavior matches the reviewed requirement and cited implementation.",
            ),
            (
                "negative",
                "Supply a missing, malformed or unauthorized input relevant to the cited implementation. Record the response and any state changes.",
                "Behavior matches the reviewed validation or access rule. No unauthorized state change occurs; confirm this criterion during review.",
            ),
            (
                "boundary",
                "Identify bounds from the cited code. Exercise the lower bound, upper bound and nearest outside values. If no bounds exist, record this scenario as not applicable with a rationale.",
                "Boundary behavior agrees with the reviewed code rule. Undefined boundaries are raised for clarification.",
            ),
        ]:
            cases.append(
                TestCase(
                    id=stable_id("TC", requirement["id"], category),
                    requirement_id=requirement["id"],
                    title=f"{requirement['title']} — {category}",
                    category=category,
                    preconditions=[
                        "Requirements baseline reviewed; test environment and representative fixtures prepared.",
                        f"Review {requirement['module']} and evidence {', '.join(requirement['evidence_ids'])}.",
                    ],
                    steps=[
                        action,
                        "Capture input, actual output, environment, commit and evidence reference.",
                    ],
                    expected=expected,
                ).model_dump()
            )
    return cases
