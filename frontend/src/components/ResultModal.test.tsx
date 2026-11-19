import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResultModal } from "./ResultModal";
import { job, testCase } from "../test/fixtures";

describe("test evidence", () => {
  it("requires attestation and sends the selected test and baseline", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <ResultModal
        test={testCase}
        baselineHash={job.baseline_hash}
        onClose={vi.fn()}
        onSave={save}
      />,
    );
    await user.selectOptions(screen.getByLabelText("Result"), "passed");
    await user.type(
      screen.getByLabelText("Actual outcome"),
      "Observed the expected quantity",
    );
    await user.type(
      screen.getByLabelText("Evidence URL or report reference"),
      "https://ci.example/run/1",
    );
    await user.click(
      screen.getByRole("button", { name: "Record verified result" }),
    );
    expect(save).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(
      screen.getByRole("button", { name: "Record verified result" }),
    );
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        test_case_id: "TC-1",
        baseline_hash: job.baseline_hash,
        status: "passed",
        attested: true,
        evidence_reference: "https://ci.example/run/1",
      }),
    );
  });
});
