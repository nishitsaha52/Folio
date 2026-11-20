import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { job } from "../../test/fixtures";
import { AnalysisProgress } from "./AnalysisProgress";

describe("failure diagnostics", () => {
  it("keeps the interrupted export checkpoint visible alongside the reason", () => {
    const failure = {
      action: "worker_interrupted",
      created: "2026-11-20T04:00:00",
      stage: "Document export",
      stage_progress: 87,
      message: "Worker restarted",
      last_message: "Writing test plan as PDF",
    };
    render(
      <AnalysisProgress
        job={{
          ...job,
          status: "failed",
          progress: 87,
          diagnostics: {
            stage: "Document export",
            latest_failure: failure,
            history: [failure],
          },
        }}
        onBack={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Why the analysis stopped" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Last checkpoint: Writing test plan as PDF"),
    ).toBeInTheDocument();
    expect(screen.getByText("Execution history")).toBeInTheDocument();
    expect(screen.getAllByText(/Worker restarted/).length).toBeGreaterThan(0);
  });
});
