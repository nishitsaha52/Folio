import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Report } from "./Report";
import { api } from "../api";
import { job, session, testCase } from "../test/fixtures";
import type { Job } from "../types";

vi.mock("../api", () => ({ api: vi.fn() }));

function reportJob(count: number): Job {
  return {
    ...job,
    can_review: true,
    analysis: {
      commit: "a".repeat(40),
      repository: job.repository,
      private: true,
      evidence: [],
      findings: [],
      requirements: Array.from({ length: count }, (_, index) => ({
        id: `REQ-${index + 1}`,
        title: `Requirement ${index + 1}`,
        statement: "Existing requirement statement",
        confidence: "inferred",
        evidence_ids: [],
        module: "service.py",
        source: "static",
      })),
      test_cases: [],
      gaps: [],
      inventory: [],
      stats: { scanned_files: 1, reused_files: 0, languages: { Python: 1 } },
      usage: [],
      execution: null,
    },
  };
}

describe("documentation report", () => {
  it("records case evidence from the tests tab against the current baseline", async () => {
    vi.mocked(api).mockImplementation(async (path) =>
      path.endsWith("/files") ? { files: [] } : [],
    );
    const selected = reportJob(1);
    selected.analysis!.test_cases = [testCase];
    const refresh = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <Report
        job={selected}
        session={session}
        onRefresh={refresh}
        onError={vi.fn()}
        onBack={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("tab", { name: /tests/ }));
    expect(screen.getByText("unexecuted")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Record verified result" }),
    );
    const dialog = within(screen.getByRole("dialog"));
    await user.selectOptions(dialog.getByLabelText("Result"), "passed");
    await user.type(
      screen.getByLabelText("Actual outcome"),
      "Observed the expected quantity",
    );
    await user.type(
      screen.getByLabelText("Evidence URL or report reference"),
      "https://ci.example/run/1",
    );
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      dialog.getByRole("button", { name: "Record verified result" }),
    );
    const request = vi
      .mocked(api)
      .mock.calls.find(([path]) => path === "/jobs/job-1/results");
    expect(request?.[1]?.method).toBe("POST");
    expect(JSON.parse(request?.[1]?.body as string)).toEqual(
      expect.objectContaining({
        test_case_id: testCase.id,
        baseline_hash: job.baseline_hash,
        status: "passed",
        attested: true,
      }),
    );
    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("lets reviewers reach records beyond the first hundred and resets paging on search", async () => {
    vi.mocked(api).mockImplementation(async (path) =>
      path.endsWith("/files") ? { files: [] } : [],
    );
    const user = userEvent.setup();
    render(
      <Report
        job={reportJob(105)}
        session={session}
        onRefresh={vi.fn()}
        onError={vi.fn()}
        onBack={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("tab", { name: /requirements/ }));
    expect(screen.getByText("REQ-1")).toBeInTheDocument();
    expect(screen.queryByText("REQ-105")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("REQ-105")).toBeInTheDocument();
    expect(screen.queryByText("REQ-1")).not.toBeInTheDocument();
    fireEvent.change(
      screen.getByRole("textbox", { name: "Search requirements" }),
      {
        target: { value: "REQ-1" },
      },
    );
    expect(screen.getByText("REQ-1")).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Record pages" }),
    ).not.toBeInTheDocument();
  });

  it("submits edits against the current baseline and refreshes after saving", async () => {
    vi.mocked(api).mockImplementation(async (path) =>
      path.endsWith("/files") ? { files: [] } : [],
    );
    const refresh = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <Report
        job={reportJob(1)}
        session={session}
        onRefresh={refresh}
        onError={vi.fn()}
        onBack={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("tab", { name: /requirements/ }));
    await user.click(screen.getByRole("button", { name: "Edit requirement" }));
    await user.clear(screen.getByLabelText("Requirement statement"));
    await user.type(
      screen.getByLabelText("Requirement statement"),
      "Updated after reviewing implementation",
    );
    await user.type(
      screen.getByLabelText("Reason for change"),
      "Clarified behavior",
    );
    await user.click(
      screen.getByRole("button", { name: "Save a new baseline" }),
    );
    expect(api).toHaveBeenCalledWith("/jobs/job-1/requirements/REQ-1", {
      method: "PATCH",
      body: JSON.stringify({
        statement: "Updated after reviewing implementation",
        rationale: "Clarified behavior",
        baseline_hash: job.baseline_hash,
      }),
    });
    expect(refresh).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
