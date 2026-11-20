"""Rebuild a readable, unapproved package from an existing saved analysis.

Usage: python scripts/regenerate_documentation.py --input repository-documentation --output .data/readable-package
The input is never modified. Existing approvals/results are not transferred to
the new capability baseline. No GitHub, AI provider or database access is needed.
"""

import argparse
import json
from pathlib import Path

from docagent.db import digest
from docagent.documents import export_package
from docagent.reporting import refine_analysis
from docagent.schemas import AnalysisConfig
from docagent.workflow import baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Use a separate output directory so the source package is preserved")
    raw = json.loads((args.input / "06-analysis/Repository_Analysis_Summary.json").read_text(encoding="utf-8"))
    analysis = refine_analysis(raw)
    baseline_hash = baseline(analysis)
    state = {
        "baseline_hash": baseline_hash, "requirements_status": "pending", "uat_status": "pending",
        "acceptance_hash": digest([baseline_hash, None, {}]), "reviews": [], "results": [],
        "counts": {"passed": 0, "failed": 0, "blocked": 0, "unexecuted": len(analysis["test_cases"])},
        "ready_for_acceptance": False,
    }
    export_package(args.output, analysis, AnalysisConfig(repository=analysis["repository"], formats=["md", "docx", "pdf"]), state, 1)
    print(json.dumps({"output": str(args.output.resolve()), "capabilities": len(analysis["requirements"]),
                      "scenarios": len(analysis["test_cases"]), "baseline": baseline_hash}))


if __name__ == "__main__":
    main()
