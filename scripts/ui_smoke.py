"""Optional browser acceptance check: pip install playwright; playwright install chromium."""

import argparse
import json
import zipfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--channel", default=None)
parser.add_argument("--output", type=Path, default=Path(".data/ui-check"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(channel=args.channel, headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(args.url, wait_until="networkidle")
    expect(page.get_by_role("heading", name="Your codebase. Clearly documented.")).to_be_visible()
    page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
    page.get_by_role("button", name="Explore the demo").click()
    expect(page.get_by_role("link", name="Download package")).to_be_visible(timeout=120000)
    page.screenshot(path=str(args.output / "report.png"), full_page=True)
    with page.expect_download() as download:
        page.get_by_role("link", name="Download package").click()
    download.value.save_as(args.output / "demo-package.zip")
    with zipfile.ZipFile(args.output / "demo-package.zip") as archive:
        assert any(name.endswith(".docx") for name in archive.namelist())
        assert any(name.endswith(".pdf") for name in archive.namelist())
        assert any(name.endswith(".xlsx") for name in archive.namelist())
        artifact_count = len(archive.namelist())
    page.get_by_role("tab", name="tests").click()
    expect(page.locator(".requirement-card").first).to_contain_text("unexecuted")
    page.get_by_role("tab", name="documents").click()
    page.get_by_role("button", name="Preview", exact=True).first.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_role("button", name="Close dialog").click()
    page.get_by_role("tab", name="diagrams").click()
    diagrams = page.locator(".diagram-grid img")
    expect(diagrams).to_have_count(4)
    for diagram in diagrams.all():
        expect(diagram).to_have_js_property("complete", True)
        expect(diagram).not_to_have_js_property("naturalWidth", 0)
    page.screenshot(path=str(args.output / "diagrams.png"), full_page=True)
    page.get_by_role("button", name="Review baseline").click()
    expect(page.get_by_role("button", name="Record review")).to_be_disabled()
    page.get_by_role("button", name="Close dialog").click()
    page.get_by_role("button", name="Workspace", exact=True).first.click()
    # A mock is used only for configuration UI validation; the demo above is a real backend run.
    fixture = {
        "name": "project",
        "owner": "example",
        "full_name": "example/project",
        "private": False,
        "description": "UI fixture",
        "default_branch": "main",
        "language": "Python",
        "updated_at": "2026-11-18T00:00:00Z",
        "url": "https://github.com/example/project",
    }
    page.route("**/api/repositories/example/project", lambda route: route.fulfill(json=fixture))
    page.route(
        "**/api/repositories/example/project/refs",
        lambda route: route.fulfill(json={"items": [{"name": "main"}], "has_next": False}),
    )
    page.get_by_label("GitHub repository URL").fill("example/project")
    page.get_by_role("button", name="Open repository").click()
    expect(page.get_by_role("heading", name="Make the code speak.")).to_be_visible()
    expect(page.get_by_role("button", name="Generate documentation")).to_be_enabled()
    page.screenshot(path=str(args.output / "configure.png"), full_page=True)
    mobile = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=1
    )
    mobile_page = mobile.new_page()
    mobile_page.goto(args.url, wait_until="networkidle")
    assert mobile_page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), (
        "Mobile horizontal overflow"
    )
    mobile_page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
    assert not errors, errors
    (args.output / "results.json").write_text(
        json.dumps(
            {
                "javascript_errors": errors,
                "downloaded_artifacts": artifact_count,
                "checks": [
                    "desktop",
                    "real demo generation",
                    "ZIP export",
                    "unexecuted tests",
                    "document preview",
                    "SVG diagrams",
                    "approval disabled without identity",
                    "configuration form",
                    "mobile layout",
                ],
            },
            indent=2,
        )
    )
    print(json.dumps({"status": "passed", "artifacts": artifact_count, "screenshots": str(args.output)}))
    browser.close()
