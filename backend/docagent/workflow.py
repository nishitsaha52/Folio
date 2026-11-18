from sqlalchemy import select

from docagent.db import Review, TestResult, digest


def baseline(analysis):
    return digest({k: analysis[k] for k in ("commit", "requirements", "test_cases")})


def workflow(db, job):
    reviews = db.scalars(select(Review).where(Review.job_id == job.id).order_by(Review.id)).all()
    results = db.scalars(select(TestResult).where(TestResult.job_id == job.id).order_by(TestResult.id)).all()
    latest = {}
    for result in results:
        if result.baseline_hash == job.baseline_hash:
            latest[result.test_case_id] = {
                "id": result.id,
                "test_case_id": result.test_case_id,
                "status": result.status,
                "source": result.source,
                "actual": result.actual,
                "evidence_reference": result.evidence_reference,
                "severity": result.severity,
                "reviewer": result.reviewer,
                "created": result.created.isoformat(),
            }
    requirements_status = "pending"
    req_decision = None
    for review in reviews:
        if (
            review.stage == "requirements"
            and review.baseline_hash == job.baseline_hash
            and review.decision != "comment"
        ):
            requirements_status = review.decision
            req_decision = review.id
    acceptance_hash = digest([job.baseline_hash, req_decision, latest])
    uat_status = "pending"
    for review in reviews:
        if review.stage == "uat" and review.baseline_hash == acceptance_hash and review.decision != "comment":
            uat_status = review.decision
    cases = (job.analysis or {}).get("test_cases", [])
    counts = {"passed": 0, "failed": 0, "blocked": 0, "unexecuted": 0}
    for case in cases:
        counts[latest.get(case["id"], {}).get("status", "unexecuted")] += 1
    return {
        "requirements_status": requirements_status,
        "uat_status": uat_status,
        "acceptance_hash": acceptance_hash,
        "results": list(latest.values()),
        "counts": counts,
        "ready_for_acceptance": bool(cases)
        and requirements_status == "approved"
        and counts["passed"] == len(cases),
        "reviews": [
            {
                "id": r.id,
                "stage": r.stage,
                "decision": r.decision,
                "reviewer": r.reviewer,
                "comment": r.comment,
                "baseline_hash": r.baseline_hash,
                "created": r.created.isoformat(),
                "current": r.baseline_hash
                == (job.baseline_hash if r.stage == "requirements" else acceptance_hash),
            }
            for r in reviews
        ],
    }
