import { useEffect, useState } from "react";
import { api } from "../api";
import type { Artifact, AuditEntry, Job } from "../types";
export function useReportArtifacts(
  job: Job,
  onError: (message: string) => void,
) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    if (job.status === "completed") {
      api<{ files: Artifact[] }>(`/jobs/${job.id}/files`, {
        signal: controller.signal,
      })
        .then((r) => {
          if (!controller.signal.aborted) setArtifacts(r.files);
        })
        .catch((e) => {
          if (!controller.signal.aborted) onError(e.message);
        });
      api<typeof audit>(`/jobs/${job.id}/audit`, { signal: controller.signal })
        .then((rows) => {
          if (!controller.signal.aborted) setAudit(rows);
        })
        .catch((e) => {
          if (!controller.signal.aborted) onError(e.message);
        });
    }
    return () => controller.abort();
  }, [job.id, job.version, job.status, onError]);
  return { artifacts, audit };
}
