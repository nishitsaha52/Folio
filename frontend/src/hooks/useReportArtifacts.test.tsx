import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { job } from "../test/fixtures";
import type { Artifact } from "../types";
import { useReportArtifacts } from "./useReportArtifacts";

vi.mock("../api", () => ({ api: vi.fn() }));

describe("report artifact loading", () => {
  it("ignores old files and audit responses after the selected report changes", async () => {
    let finishFiles!: (value: { files: Artifact[] }) => void;
    let finishAudit!: (value: unknown[]) => void;
    vi.mocked(api).mockImplementation((path) => {
      if (path === "/jobs/old/files")
        return new Promise((resolve) => {
          finishFiles = resolve as typeof finishFiles;
        });
      if (path === "/jobs/old/audit")
        return new Promise((resolve) => {
          finishAudit = resolve as typeof finishAudit;
        });
      return Promise.resolve(
        path.endsWith("/files")
          ? { files: [{ path: "current.md", bytes: 1 }] }
          : [],
      );
    });
    const error = vi.fn();
    const { result, rerender } = renderHook(
      ({ id }) => useReportArtifacts({ ...job, id }, error),
      { initialProps: { id: "old" } },
    );
    const signal = vi.mocked(api).mock.calls[0][1]?.signal;
    rerender({ id: "current" });
    await waitFor(() =>
      expect(result.current.artifacts).toEqual([
        { path: "current.md", bytes: 1 },
      ]),
    );
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      finishFiles({ files: [{ path: "old.md", bytes: 1 }] });
      finishAudit([{ id: 1, action: "old response" }]);
    });
    expect(result.current.artifacts).toEqual([
      { path: "current.md", bytes: 1 },
    ]);
    expect(result.current.audit).toEqual([]);
    expect(error).not.toHaveBeenCalled();
  });
});
