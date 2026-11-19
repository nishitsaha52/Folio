import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentsTab } from "./DocumentsTab";
import { api } from "../../api";
import { job } from "../../test/fixtures";

vi.mock("../../api", () => ({ api: vi.fn() }));

const artifacts = [
  { path: "01-requirements/Requirements.md", bytes: 1024 },
  { path: "01-requirements/Requirements.pdf", bytes: 2048 },
];
const download = (path = "", version = 2) =>
  `/api/jobs/job-1/download?${new URLSearchParams({ path, version: String(version) })}`;

describe("document artifacts", () => {
  it("previews Markdown, closes the preview and links downloads to the current version", async () => {
    vi.mocked(api).mockResolvedValue({
      content: "# Reviewed requirements\n\nSource evidence retained.",
    });
    const user = userEvent.setup();
    render(
      <DocumentsTab
        job={{ ...job, version: 2, versions: [1, 2] }}
        artifacts={artifacts}
        download={download}
        onError={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("link", {
        name: "Download 01-requirements/Requirements.pdf",
      }),
    ).toHaveAttribute("href", download(artifacts[1].path));
    expect(
      screen.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["Version history", "Download version 2", "Download version 1"]);
    await user.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByRole("heading", { name: "Reviewed requirements" });
    expect(api).toHaveBeenCalledWith(
      "/jobs/job-1/preview?path=01-requirements%2FRequirements.md",
    );
    await user.click(screen.getByRole("button", { name: "Close dialog" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reports preview failures without opening a dialog", async () => {
    vi.mocked(api).mockRejectedValue(new Error("Artifact unavailable"));
    const onError = vi.fn();
    const user = userEvent.setup();
    render(
      <DocumentsTab
        job={job}
        artifacts={artifacts}
        download={download}
        onError={onError}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onError).toHaveBeenCalledWith("Artifact unavailable");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
