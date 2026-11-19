import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Configure } from "./Configure";
import { api } from "../api";
import { repository, session } from "../test/fixtures";

vi.mock("../api", () => ({ api: vi.fn() }));

describe("analysis configuration", () => {
  it("requires private-code consent for the selected provider and fallback", async () => {
    vi.mocked(api).mockResolvedValue({ items: [{ name: "main" }] });
    const submit = vi.fn();
    const user = userEvent.setup();
    render(
      <Configure
        repository={repository}
        session={session}
        busy={false}
        onBack={vi.fn()}
        onSubmit={submit}
        onError={vi.fn()}
      />,
    );
    await user.selectOptions(screen.getByLabelText("Provider"), "openai");
    await user.selectOptions(
      screen.getByLabelText("Fallback provider"),
      "anthropic",
    );
    await user.click(
      screen.getByRole("button", { name: "Generate documentation" }),
    );
    expect(submit).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("checkbox", { name: /I authorize sending/ }),
    );
    await user.click(
      screen.getByRole("button", { name: "Generate documentation" }),
    );
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        repository: "team/project",
        ref: "main",
        consent_providers: ["openai", "anthropic"],
        providers: [
          { provider: "openai", model: "primary-model" },
          { provider: "anthropic", model: "fallback-model" },
        ],
        execute_tests: false,
      }),
    );
  });

  it("prevents submission without deliverables and disables unconfigured execution", async () => {
    vi.mocked(api).mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(
      <Configure
        repository={repository}
        session={session}
        busy={false}
        onBack={vi.fn()}
        onSubmit={vi.fn()}
        onError={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("checkbox", { name: "Run existing repository tests" }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(
      screen.getByRole("button", { name: "Generate documentation" }),
    ).toBeDisabled();
  });

  it("reports reference-loading errors", async () => {
    vi.mocked(api).mockRejectedValue(new Error("Repository access denied"));
    const error = vi.fn();
    render(
      <Configure
        repository={repository}
        session={session}
        busy={false}
        onBack={vi.fn()}
        onSubmit={vi.fn()}
        onError={error}
      />,
    );
    await waitFor(() =>
      expect(error).toHaveBeenCalledWith("Repository access denied"),
    );
  });
});
