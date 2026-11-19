import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { job } from "../test/fixtures";
import type { Job } from "../types";
import { useJobPolling } from "./useJobPolling";

vi.mock("../api", () => ({ api: vi.fn() }));
afterEach(() => vi.useRealTimers());

describe("job polling", () => {
  it("refreshes history on completion and stops polling", async () => {
    vi.useFakeTimers();
    vi.mocked(api).mockResolvedValue(job);
    const update = vi.fn(),
      complete = vi.fn().mockResolvedValue(undefined),
      error = vi.fn();
    renderHook(() =>
      useJobPolling({ ...job, status: "running" }, update, complete, error),
    );
    await act(() => vi.advanceTimersByTimeAsync(1800));
    expect(update).toHaveBeenCalledWith(job);
    expect(complete).toHaveBeenCalledOnce();
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api).toHaveBeenCalledOnce();
    expect(error).not.toHaveBeenCalled();
  });

  it("ignores a late response after switching jobs", async () => {
    vi.useFakeTimers();
    let resolve!: (job: Job) => void;
    vi.mocked(api).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done as (job: Job) => void;
        }),
    );
    const update = vi.fn(),
      complete = vi.fn().mockResolvedValue(undefined),
      error = vi.fn();
    const { rerender, unmount } = renderHook(
      ({ id }) =>
        useJobPolling(
          { ...job, id, status: "running" },
          update,
          complete,
          error,
        ),
      { initialProps: { id: "old-job" } },
    );
    await act(() => vi.advanceTimersByTimeAsync(1800));
    const signal = vi.mocked(api).mock.calls[0][1]?.signal;
    rerender({ id: "new-job" });
    expect(signal?.aborted).toBe(true);
    await act(async () => resolve({ ...job, id: "old-job" }));
    expect(update).not.toHaveBeenCalled();
    expect(complete).not.toHaveBeenCalled();
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(api).toHaveBeenCalledOnce();
  });
});
