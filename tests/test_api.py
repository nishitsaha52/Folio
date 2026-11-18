import io
import zipfile

from openpyxl import load_workbook


def test_csrf_and_secret_validation(client):
    response = client.post("/api/auth/pat", json={"token": "secret"}, headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403
    response = client.post("/api/auth/pat", json={"token": "secret"})
    assert response.status_code == 422
    assert "secret" not in response.text


def test_demo_exports_and_isolation(client, completed):
    job_id = completed["id"]
    assert completed["workflow"]["requirements_status"] == "pending"
    assert completed["workflow"]["counts"]["passed"] == 0
    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert any(n.endswith("Software_Requirements_Specification.docx") for n in z.namelist())
        assert any(n.endswith("DFD_Level_2.svg") for n in z.namelist())
        assert any(n.endswith("Technology_Stack.pdf") for n in z.namelist())
        rtm = next(n for n in z.namelist() if n.endswith(".xlsx"))
        wb = load_workbook(io.BytesIO(z.read(rtm)))
        assert wb.active["G2"].value == "unexecuted"
    assert (
        client.get(f"/api/jobs/{job_id}/download", params={"path": "../../.encryption-key"}).status_code
        == 400
    )
    client.cookies.clear()
    client.get("/api/session")
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/download").status_code == 404


def test_no_automatic_approval(client, completed):
    job_id = completed["id"]
    response = client.post(
        f"/api/jobs/{job_id}/reviews",
        json={
            "stage": "requirements",
            "decision": "approved",
            "comment": "I approve",
            "baseline_hash": completed["baseline_hash"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 403


def test_baseline_edit_invalidates_approval(client, completed, reviewer):
    job_id = completed["id"]
    response = client.post(
        f"/api/jobs/{job_id}/reviews",
        json={
            "stage": "requirements",
            "decision": "approved",
            "comment": "Requirements checked against evidence",
            "baseline_hash": completed["baseline_hash"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["workflow"]["requirements_status"] == "approved"
    req_id = completed["analysis"]["requirements"][0]["id"]
    response = client.patch(
        f"/api/jobs/{job_id}/requirements/{req_id}",
        json={
            "statement": "Updated requirement after source review",
            "rationale": "Clarified intended application behavior",
            "baseline_hash": completed["baseline_hash"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["workflow"]["requirements_status"] == "pending"
    assert response.json()["baseline_hash"] != completed["baseline_hash"]
    assert client.get(f"/api/jobs/{job_id}/download", params={"version": 1}).status_code == 200


def test_uat_cannot_approve_without_evidence(client, completed, reviewer):
    response = client.post(
        f"/api/jobs/{completed['id']}/reviews",
        json={
            "stage": "uat",
            "decision": "approved",
            "comment": "Would like to accept",
            "baseline_hash": completed["workflow"]["acceptance_hash"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 409


def test_recorded_result_needs_attestation(client, completed, reviewer):
    response = client.post(
        f"/api/jobs/{completed['id']}/results",
        json={
            "baseline_hash": completed["baseline_hash"],
            "test_case_id": completed["analysis"]["test_cases"][0]["id"],
            "status": "passed",
            "actual": "Verified actual result",
            "evidence_reference": "https://ci.example/run/1",
            "source": "existing_report",
            "attested": False,
        },
    )
    assert response.status_code == 422


def test_uncommitted_version_is_not_downloadable(client, completed):
    from docagent.jobs import output_root

    root = output_root(completed["id"], 2)
    root.mkdir()
    (root / "manifest.json").write_text("{}")
    (root / "pretend-approval.md").write_text("Uncommitted output")
    response = client.get(
        f"/api/jobs/{completed['id']}/download", params={"version": 2, "path": "pretend-approval.md"}
    )
    assert response.status_code == 404
