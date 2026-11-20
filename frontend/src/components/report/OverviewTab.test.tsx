import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { job } from "../../test/fixtures";
import type { Analysis } from "../../types";
import { OverviewTab } from "./OverviewTab";

describe("scan coverage disclosure", () => {
  it("shows blocked paths and makes the complete coverage report discoverable", () => {
    const analysis: Analysis = {
      repository: job.repository,
      commit: "a".repeat(40),
      private: true,
      evidence: [],
      findings: [],
      requirements: [],
      test_cases: [],
      gaps: [],
      inventory: [],
      usage: [],
      execution: null,
      stats: { scanned_files: 2, reused_files: 0, languages: {} },
      scope: {
        partial: true,
        skipped_files: [
          {
            path: "backend/tests/test_scanner_worker.py",
            reason: "unreadable_file",
            code: 22,
            message:
              "The operating system prevented access. It was not inspected.",
          },
        ],
        auto_exclusions: [
          {
            path: "static/react/assets/main-9eRkOz9F.js",
            reason: "Fingerprinted browser build output",
          },
        ],
        suggested_ignore_patterns: ["static/react/assets/**"],
      },
    };
    render(<OverviewTab analysis={analysis} state={job.workflow!} />);
    expect(
      screen.getByRole("heading", { name: "Documentation has coverage gaps" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("backend/tests/test_scanner_worker.py"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Scope_Report.json/).length).toBeGreaterThan(0);
    expect(
      screen.getByText("Suggested .docagentignore rules"),
    ).toBeInTheDocument();
  });
});
