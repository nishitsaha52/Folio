import { useEffect, useState } from "react";
import { api } from "../api";
import type { Repository } from "../types";
export function useRepositories(
  login: string | null | undefined,
  onError: (message: string) => void,
) {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [repoLoading, setRepoLoading] = useState(false);
  useEffect(() => {
    if (!login) {
      setRepos([]);
      return;
    }
    let cancelled = false;
    setRepoLoading(true);
    (async () => {
      const all: Repository[] = [];
      for (let p = 1; p <= 1000; p++) {
        const data = await api<{ items: Repository[]; has_next: boolean }>(
          `/repositories?page=${p}`,
        );
        if (cancelled) return;
        all.push(...data.items);
        setRepos([...new Map(all.map((r) => [r.full_name, r])).values()]);
        if (!data.has_next) break;
      }
    })()
      .catch((e) => {
        if (!cancelled) onError(e.message);
      })
      .finally(() => {
        if (!cancelled) setRepoLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [login, onError]);
  return { repos, repoLoading };
}
