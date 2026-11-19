import { useEffect } from "react";
import { api } from "../api";
import type { Job } from "../types";

const active = (job: Job) => ["queued", "running"].includes(job.status);

export function useJobPolling(
  job: Job | null,
  onUpdate: (job: Job) => void,
  onComplete: () => Promise<void>,
  onError: (message: string) => void,
) {
  const id = job?.id;
  const running = job ? active(job) : false;
  useEffect(() => {
    if (!id || !running) return;
    let cancelled = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Job>(`/jobs/${id}`, {
          signal: controller.signal,
        });
        if (cancelled) return;
        onUpdate(next);
        if (!active(next)) {
          await onComplete();
          return;
        }
      } catch (error) {
        if (cancelled) return;
        onError((error as Error).message);
      }
      if (!cancelled) timer = setTimeout(poll, 1800);
    }
    timer = setTimeout(poll, 1800);
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, running, onUpdate, onComplete, onError]);
}
