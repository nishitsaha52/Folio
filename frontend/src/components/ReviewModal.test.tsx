import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReviewModal } from "./ReviewModal";
import { job } from "../test/fixtures";

describe("human review", () => {
  it("blocks anonymous decisions", () => {
    render(
      <ReviewModal
        job={job}
        canReview={false}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Record review" }),
    ).toBeDisabled();
  });

  it("binds an acknowledged approval to the requirements baseline", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ReviewModal job={job} canReview onClose={vi.fn()} onSave={save} />);
    await user.selectOptions(screen.getByLabelText("Decision"), "approved");
    await user.type(
      screen.getByLabelText("Review comment"),
      "Checked against source evidence",
    );
    await user.click(screen.getByRole("button", { name: "Record review" }));
    expect(save).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Record review" }));
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        stage: "requirements",
        decision: "approved",
        acknowledged: true,
        baseline_hash: job.baseline_hash,
      }),
    );
  });

  it("cannot carry a requirements approval into an unready UAT stage", async () => {
    const user = userEvent.setup();
    render(
      <ReviewModal job={job} canReview onClose={vi.fn()} onSave={vi.fn()} />,
    );
    await user.selectOptions(screen.getByLabelText("Decision"), "approved");
    await user.selectOptions(screen.getByLabelText("Review stage"), "uat");
    expect(
      screen.getByRole("button", { name: "Record review" }),
    ).toBeDisabled();
  });
});
