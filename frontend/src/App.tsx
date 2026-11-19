import { useCallback, useEffect, useState } from "react";
import type { Job, Repository, Session } from "./types";
import { api, post, repositoryName, setCsrf } from "./api";
import { useJobPolling } from "./hooks/useJobPolling";
import { useRepositories } from "./hooks/useRepositories";
import { AppShell, type AppPage } from "./components/AppShell";
import { AuthDialog } from "./components/AuthDialog";
import { Configure } from "./components/Configure";
import { Report } from "./components/Report";
import { WorkspaceIntro } from "./components/workspace/WorkspaceIntro";
import {
  RepositoryPicker,
  type RepositoryFilters,
} from "./components/workspace/RepositoryPicker";
import { WorkspaceFooter } from "./components/workspace/WorkspaceFooter";
export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [page, setPage] = useState<AppPage>("workspace");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Repository | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [auth, setAuth] = useState(false);
  const [token, setToken] = useState("");

  const refreshSession = useCallback(async () => {
    const s = await api<Session>("/session");
    setCsrf(s.csrf_token);
    setSession(s);
    return s;
  }, []);
  const refreshJobs = useCallback(
    async () => setJobs(await api<Job[]>("/jobs")),
    [],
  );
  useEffect(() => {
    refreshSession()
      .then(refreshJobs)
      .catch((e) => setError(e.message));
  }, [refreshSession, refreshJobs]);
  const { repos, repoLoading } = useRepositories(session?.login, setError);
  const [filters, setFilters] = useState<RepositoryFilters>({
    search: "",
    visibility: "all",
    owner: "all",
    publicRepo: "",
  });
  useJobPolling(job, setJob, refreshJobs, setError);

  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openJob(id: string) {
    await act(async () => {
      setJob(await api<Job>(`/jobs/${id}`));
      setPage("report");
    });
  }
  async function demo() {
    await act(async () => {
      setJob(await post<Job>("/demo"));
      setPage("report");
      await refreshJobs();
    });
  }
  function choose(repo: Repository) {
    setSelected(repo);
    setPage("configure");
    setError("");
  }
  const completed = jobs.filter((j) => j.status === "completed").length;

  function openRepository(value: string) {
    return act(async () => {
      const name = repositoryName(value);
      if (!/^[\w.-]+\/[\w.-]+$/.test(name))
        throw new Error(
          "Enter a GitHub repository as owner/repository or a github.com URL.",
        );
      choose(await api<Repository>(`/repositories/${name}`));
    });
  }
  function account() {
    if (!session?.login) {
      setAuth(true);
      return;
    }
    return act(async () => {
      await post("/auth/logout");
      await refreshSession();
      setJobs([]);
      setJob(null);
      setPage("workspace");
    });
  }
  return (
    <>
      <AppShell
        page={page}
        jobs={jobs}
        completed={completed}
        session={session}
        hasRepository={!!selected}
        hasJob={!!job}
        error={error}
        onNavigate={setPage}
        onOpenJob={openJob}
        onAccount={account}
        onDismissError={() => setError("")}
      >
        {page === "workspace" && (
          <>
            <WorkspaceIntro
              repositoryCount={repos.length}
              completed={completed}
              busy={busy}
              session={session}
              onDemo={demo}
            />
            <RepositoryPicker
              repos={repos}
              session={session}
              busy={busy}
              repoLoading={repoLoading}
              filters={filters}
              onFiltersChange={setFilters}
              onConnect={() => setAuth(true)}
              onChoose={choose}
              onOpen={openRepository}
            />
            <WorkspaceFooter />
          </>
        )}
        {page === "configure" && selected && session && (
          <Configure
            key={selected.full_name}
            repository={selected}
            session={session}
            busy={busy}
            onBack={() => setPage("workspace")}
            onSubmit={(config) =>
              act(async () => {
                setJob(await post<Job>("/jobs", config));
                setPage("report");
                await refreshJobs();
              })
            }
            onError={setError}
          />
        )}
        {page === "report" && job && (
          <Report
            key={job.id}
            job={job}
            session={session}
            onRefresh={async () => {
              const updated = await api<Job>(`/jobs/${job.id}`);
              setJob((current) =>
                current?.id === updated.id ? updated : current,
              );
              await refreshJobs();
            }}
            onError={setError}
            onBack={() => setPage("workspace")}
          />
        )}
      </AppShell>
      {auth && (
        <AuthDialog
          session={session}
          busy={busy}
          token={token}
          onTokenChange={setToken}
          onClose={() => {
            setAuth(false);
            setToken("");
          }}
          onSubmit={() =>
            act(async () => {
              await post("/auth/pat", { token });
              setToken("");
              await refreshSession();
              await refreshJobs();
              setAuth(false);
            })
          }
        />
      )}
    </>
  );
}
