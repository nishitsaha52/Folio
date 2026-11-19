"""Resolve declared local imports without importing or executing repository code."""

import tomllib
from pathlib import Path, PurePosixPath


def import_edges(root: Path, inventory, imports):
    paths = {item["path"] for item in inventory}
    python_paths = {path for path in paths if path.endswith(".py")}
    roots = {PurePosixPath(".")}
    if "pyproject.toml" in paths:
        try:
            config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
            setuptools = config.get("tool", {}).get("setuptools", {})
            declared = list(setuptools.get("package-dir", {}).values())
            packages = setuptools.get("packages", {})
            if isinstance(packages, dict):
                where = packages.get("find", {}).get("where", [])
                declared.extend([where] if isinstance(where, str) else where)
            for value in declared:
                if isinstance(value, str):
                    base = PurePosixPath(value)
                    if not base.is_absolute() and ".." not in base.parts and "\\" not in value and ":" not in value:
                        roots.add(base)
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # Malformed packaging configuration does not prevent syntax inspection.
    for path in python_paths:
        package = PurePosixPath(path).parent
        if package.name in {"src", "backend", "lib"}:
            roots.add(package)
        for parent in PurePosixPath(path).parents:
            if parent.name in {"src", "backend", "lib"}:
                roots.add(parent)
        if PurePosixPath(path).name == "__init__.py":
            while package != package.parent and (package.parent / "__init__.py").as_posix() in python_paths:
                package = package.parent
            roots.add(package.parent)

    def python_target(module):
        for candidate in (module.as_posix() + ".py", (module / "__init__.py").as_posix()):
            if candidate in python_paths:
                return candidate
        return None

    edges = []
    seen = set()
    for source, dependencies in imports.items():
        for dependency in dependencies:
            module = dependency["module"]
            targets = []
            if source.endswith(".py"):
                parent = PurePosixPath(source).parent
                level = dependency.get("level", 0)
                if level:
                    if level > len(parent.parts):
                        continue
                    base = parent
                    for _ in range(level - 1):
                        base = base.parent
                    bases = [base]
                else:
                    # Prefer the importer's own source root when multiple applications
                    # contain identically named packages. Do not invent ambiguous edges.
                    local = [base for base in roots if parent.is_relative_to(base)]
                    bases = sorted(local, key=lambda base: (-len(base.parts), base.as_posix()))
                matches = []
                for base in bases:
                    target_module = base / module.replace(".", "/")
                    direct = python_target(target_module)
                    named = [
                        python_target(target_module / name)
                        for name in dependency.get("names", []) if name != "*"
                    ]
                    found = [target for target in [direct, *named] if target]
                    if found:
                        targets = found
                        break
                if not targets and not level:
                    for base in sorted(roots - set(local), key=lambda base: base.as_posix()):
                        target_module = base / module.replace(".", "/")
                        found = [python_target(target_module)] + [
                            python_target(target_module / name)
                            for name in dependency.get("names", []) if name != "*"
                        ]
                        if any(found):
                            matches.append([target for target in found if target])
                    if len(matches) == 1:
                        targets = matches[0]
            elif module.startswith("."):
                target = (root / Path(source).parent / module).resolve()
                if target.is_relative_to(root):
                    relative = target.relative_to(root).as_posix()
                    candidates = [relative] + [
                        relative + suffix
                        for suffix in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")
                    ]
                    targets = next(([candidate] for candidate in candidates if candidate in paths), [])
            for target in targets:
                identity = (source, target, dependency["line"])
                if source != target and identity not in seen:
                    seen.add(identity)
                    edges.append({
                        "source": source, "target": target, "kind": "imports",
                        "line": dependency["line"], "confidence": "verified",
                    })
    return edges
