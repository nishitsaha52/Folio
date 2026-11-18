import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Code2,
  FileCode2,
  FileText,
  FolderGit2,
  GitBranch,
  Github,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Network,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, post, repositoryName, setCsrf } from "./api";
import type {
  Artifact,
  Case,
  DocKind,
  Evidence,
  Job,
  Provider,
  Repository,
  Requirement,
  Session,
} from "./types";
import "./styles.css";

const DOCS: {
  id: DocKind;
  title: string;
  description: string;
  icon: typeof FileText;
}[] = [
  {
    id: "srs",
    title: "Requirements specification",
    description: "As-is functionality and business rules",
    icon: FileText,
  },
  {
    id: "requirements_signoff",
    title: "Requirements sign-off",
    description: "Baseline review and human approval",
    icon: CheckCheck,
  },
  {
    id: "test_cases",
    title: "Test cases & UAT report",
    description: "Scenarios and requirements traceability",
    icon: ShieldCheck,
  },
  {
    id: "uat_signoff",
    title: "Application acceptance",
    description: "UAT outcomes and stakeholder decisions",
    icon: CheckCheck,
  },
  {
    id: "architecture",
    title: "System architecture",
    description: "Components and their relationships",
    icon: Layers3,
  },
  {
    id: "data_flow",
    title: "Data flow diagrams",
    description: "Context, processes and handler detail",
    icon: Network,
  },
  {
    id: "technology",
    title: "Technology stack",
    description: "Languages, frameworks and dependencies",
    icon: Code2,
  },
];
const providerNames = {
  openai: "OpenAI",
  anthropic: "Anthropic Claude",
  gemini: "Google Gemini",
};
const time = (value: string) =>
  new Date(value.endsWith("Z") ? value : value + "Z").toLocaleString();
const human = (value: string) => value.replaceAll("_", " ");
const Badge = ({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) => <span className={`badge ${tone}`}>{children}</span>;

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [page, setPage] = useState<"workspace" | "configure" | "report">(
    "workspace",
  );
  const [jobs, setJobs] = useState<Job[]>([]);
  const [repos, setRepos] = useState<Repository[]>([]);
  const [selected, setSelected] = useState<Repository | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [repoLoading, setRepoLoading] = useState(false);
  const [auth, setAuth] = useState(false);
  const [token, setToken] = useState("");
  const [search, setSearch] = useState("");
  const [visibility, setVisibility] = useState("all");
  const [owner, setOwner] = useState("all");
  const [publicRepo, setPublicRepo] = useState("");

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
  useEffect(() => {
    if (!session?.login) {
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
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setRepoLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session?.login]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(
      () =>
        api<Job>(`/jobs/${job.id}`)
          .then((next) => {
            setJob(next);
            if (next.status !== "running" && next.status !== "queued")
              refreshJobs();
          })
          .catch((e) => setError(e.message)),
      1800,
    );
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status, refreshJobs]);

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
  const filtered = repos.filter(
    (r) =>
      (r.full_name + " " + r.description)
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (visibility === "all" || r.private === (visibility === "private")) &&
      (owner === "all" || r.owner === owner),
  );
  const completed = jobs.filter((j) => j.status === "completed").length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setPage("workspace")}>
          <span className="brand-icon">
            <BookOpen size={23} />
          </span>
          <span>
            folio<span className="brand-dot">.</span>
          </span>
        </button>
        <div className="workspace-label">REPOSITORY INTELLIGENCE</div>
        <nav aria-label="Main navigation">
          <button
            className={page === "workspace" ? "active" : ""}
            onClick={() => setPage("workspace")}
          >
            <LayoutDashboard size={18} /> Workspace
          </button>
          <button
            className={page === "configure" ? "active" : ""}
            onClick={() =>
              selected ? setPage("configure") : setPage("workspace")
            }
          >
            <Plus size={18} /> New analysis
          </button>
          <button
            className={page === "report" ? "active" : ""}
            onClick={() => (job ? setPage("report") : setPage("workspace"))}
          >
            <FileText size={18} /> Documentation{" "}
            <span className="nav-count">{completed}</span>
          </button>
        </nav>
        <div className="sidebar-rule" />
        <div className="small-label">RECENT ANALYSES</div>
        <div className="recent-list">
          {jobs.slice(0, 5).map((j) => (
            <button key={j.id} onClick={() => openJob(j.id)}>
              <span className={`status-dot ${j.status}`} />
              <span>{j.repository.split("/")[1]}</span>
              <ChevronRight size={13} />
            </button>
          ))}
          {jobs.length === 0 && <p>Your analyses will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <ShieldCheck size={19} />
            <strong>Evidence comes first</strong>
            <p>Every finding has a source. Every approval stays human.</p>
          </div>
          <button
            className="account"
            onClick={() =>
              session?.login
                ? act(async () => {
                    await post("/auth/logout");
                    await refreshSession();
                    setJobs([]);
                    setJob(null);
                    setPage("workspace");
                  })
                : setAuth(true)
            }
          >
            <span className="avatar">
              {session?.login?.slice(0, 2).toUpperCase() || (
                <Github size={18} />
              )}
            </span>
            <span>
              <strong>{session?.login || "Connect GitHub"}</strong>
              <small>
                {session?.login
                  ? "Authenticated workspace"
                  : "Public & private repositories"}
              </small>
            </span>
            {session?.login ? <LogOut size={15} /> : <ChevronRight size={15} />}
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="topbar-parent">Workspace</span>
            <ChevronRight size={14} />
            <span>
              {page === "configure"
                ? "New analysis"
                : page === "report"
                  ? "Documentation"
                  : "Overview"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="live-dot" />{" "}
            {session?.login ? "GitHub connected" : "Local workspace"}
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              aria-label="API documentation"
            >
              <CircleHelp size={18} />
            </a>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {page === "workspace" && (
            <>
              <section className="hero">
                <div>
                  <div className="eyebrow">
                    <span /> FROM SOURCE TO SHARED UNDERSTANDING
                  </div>
                  <h1>
                    Your codebase.
                    <br />
                    <em>Clearly documented.</em>
                  </h1>
                  <p>
                    Turn a repository into requirements, architecture, and test
                    documentation. Grounded in code. Ready for human review.
                  </p>
                  <div className="hero-actions">
                    <button
                      className="primary"
                      onClick={() =>
                        document.getElementById("repository-input")?.focus()
                      }
                    >
                      <Plus size={17} /> Start an analysis
                    </button>
                    <button
                      className="text-button"
                      disabled={busy || !session}
                      onClick={demo}
                    >
                      Explore the demo <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
                <div className="hero-illustration" aria-hidden="true">
                  <div className="source-card">
                    <FolderGit2 size={23} />
                    <div>
                      <strong>Repository</strong>
                      <span>Code · configuration · tests</span>
                    </div>
                    <div className="code-line" />
                    <div className="code-line short" />
                  </div>
                  <div className="connector">
                    <span />
                    <Sparkles size={19} />
                    <span />
                  </div>
                  <div className="document-stack">
                    <div className="stack-back" />
                    <div className="document-card">
                      <span className="doc-label">DOCUMENTATION PACKAGE</span>
                      <div>
                        <FileText size={18} />
                        <strong>Requirements</strong>
                        <Check size={15} />
                      </div>
                      <div>
                        <Layers3 size={18} />
                        <strong>Architecture</strong>
                        <Check size={15} />
                      </div>
                      <div>
                        <ShieldCheck size={18} />
                        <strong>Test scenarios</strong>
                        <Check size={15} />
                      </div>
                      <span className="evidence-chip">
                        Linked to source evidence
                      </span>
                    </div>
                  </div>
                </div>
              </section>
              <div className="overview-stats">
                <div>
                  <span className="stat-icon">
                    <FolderGit2 size={20} />
                  </span>
                  <div>
                    <strong>{repos.length}</strong>
                    <span>Accessible repositories</span>
                  </div>
                </div>
                <div>
                  <span className="stat-icon">
                    <FileText size={20} />
                  </span>
                  <div>
                    <strong>{completed}</strong>
                    <span>Completed analyses</span>
                  </div>
                </div>
                <div>
                  <span className="stat-icon">
                    <Layers3 size={20} />
                  </span>
                  <div>
                    <strong>7</strong>
                    <span>Documentation deliverables</span>
                  </div>
                </div>
                <div>
                  <span className="stat-icon">
                    <LockKeyhole size={20} />
                  </span>
                  <div>
                    <strong>Read only</strong>
                    <span>Source access by default</span>
                  </div>
                </div>
              </div>
              <section className="repository-section">
                <div className="section-heading">
                  <div>
                    <h2>Choose your repository</h2>
                    <p>A good understanding starts at the source.</p>
                  </div>
                  {!session?.login && (
                    <button className="secondary" onClick={() => setAuth(true)}>
                      <Github size={17} /> Connect GitHub
                    </button>
                  )}
                </div>
                <form
                  className="public-repo"
                  onSubmit={(e) => {
                    e.preventDefault();
                    act(async () => {
                      const name = repositoryName(publicRepo);
                      if (!/^[\w.-]+\/[\w.-]+$/.test(name))
                        throw new Error(
                          "Enter a GitHub repository as owner/repository or a github.com URL.",
                        );
                      choose(await api<Repository>(`/repositories/${name}`));
                    });
                  }}
                >
                  <div className="input-icon">
                    <Github size={18} />
                    <input
                      id="repository-input"
                      value={publicRepo}
                      onChange={(e) => setPublicRepo(e.target.value)}
                      placeholder="Paste a GitHub URL or owner/repository"
                      aria-label="GitHub repository URL"
                      required
                    />
                  </div>
                  <button className="secondary" disabled={busy || !session}>
                    Open repository <ArrowRight size={15} />
                  </button>
                </form>
                {session?.login ? (
                  <>
                    <div className="repo-toolbar">
                      <div className="input-icon">
                        <Search size={17} />
                        <input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Search repositories…"
                          aria-label="Search repositories"
                        />
                      </div>
                      <select
                        value={owner}
                        onChange={(e) => setOwner(e.target.value)}
                        aria-label="Filter owner"
                      >
                        <option value="all">All owners</option>
                        {[...new Set(repos.map((r) => r.owner))].map((o) => (
                          <option key={o}>{o}</option>
                        ))}
                      </select>
                      <select
                        value={visibility}
                        onChange={(e) => setVisibility(e.target.value)}
                        aria-label="Filter visibility"
                      >
                        <option value="all">All visibility</option>
                        <option value="public">Public</option>
                        <option value="private">Private</option>
                      </select>
                    </div>
                    <div className="repo-grid">
                      {filtered.map((repo) => (
                        <button
                          className="repo-card"
                          key={repo.full_name}
                          onClick={() => choose(repo)}
                        >
                          <div className="repo-card-top">
                            <FolderGit2 size={23} />
                            <Badge>{repo.private ? "Private" : "Public"}</Badge>
                          </div>
                          <small>{repo.owner}</small>
                          <h3>{repo.name}</h3>
                          <p>
                            {repo.description ||
                              "No repository description provided."}
                          </p>
                          <div className="repo-card-footer">
                            <span>
                              <i className="language-dot" />
                              {repo.language || "Not specified"}
                            </span>
                            <span>
                              <GitBranch size={13} />
                              {repo.default_branch}
                            </span>
                          </div>
                          <small>
                            Updated{" "}
                            {new Date(repo.updated_at).toLocaleDateString()}
                          </small>
                        </button>
                      ))}
                    </div>
                    {repoLoading && (
                      <div className="loading-line">
                        <LoaderCircle className="spin" size={16} /> Discovering
                        accessible repositories…
                      </div>
                    )}
                    {!repoLoading && !filtered.length && (
                      <div className="empty-state">
                        No matching repositories. Try another filter or paste a
                        repository URL.
                      </div>
                    )}
                  </>
                ) : (
                  <div className="connect-state">
                    <span className="connect-github">
                      <Github size={29} />
                    </span>
                    <h3>Your repositories, in one place</h3>
                    <p>
                      Connect your GitHub account to browse repositories you own
                      <br className="desktop-only" /> and those shared by your
                      teams. Or open a public URL above.
                    </p>
                    <button
                      className="text-button"
                      onClick={() => setAuth(true)}
                    >
                      Connect your account <ArrowRight size={15} />
                    </button>
                    <div className="security-footnote">
                      <LockKeyhole size={12} /> Credentials are encrypted. Your
                      source repository stays unchanged.
                    </div>
                  </div>
                )}
              </section>
              <section className="deliverables">
                <div className="section-heading">
                  <div>
                    <h2>A complete documentation workflow</h2>
                    <p>
                      From understanding the implementation to recording
                      acceptance.
                    </p>
                  </div>
                  <Badge>MD · DOCX · PDF</Badge>
                </div>
                <div className="deliverable-grid">
                  {DOCS.slice(0, 3).map((d, i) => (
                    <div key={d.id}>
                      <span className="deliverable-number">0{i + 1}</span>
                      <d.icon size={22} />
                      <h3>{d.title}</h3>
                      <p>{d.description}</p>
                    </div>
                  ))}
                  <div>
                    <span className="deliverable-number">+4</span>
                    <Network size={22} />
                    <h3>Architecture & more</h3>
                    <p>Data flows, technology stack and acceptance.</p>
                  </div>
                </div>
              </section>
              <footer className="page-footer">
                <span>Folio · Repository Documentation Agent</span>
                <span>Traceable by design. Reviewed by people.</span>
              </footer>
            </>
          )}
          {page === "configure" && selected && session && (
            <Configure
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
              job={job}
              session={session}
              onRefresh={async () => {
                setJob(await api<Job>(`/jobs/${job.id}`));
                await refreshJobs();
              }}
              onError={setError}
              onBack={() => setPage("workspace")}
            />
          )}
        </main>
      </div>
      {auth && (
        <Modal
          title="Connect your GitHub account"
          onClose={() => {
            setAuth(false);
            setToken("");
          }}
        >
          <p className="muted">
            Use a fine-grained token with read access to repository contents and
            metadata. It is encrypted on the server and never saved in browser
            storage.
          </p>
          {session?.oauth_enabled && (
            <a className="primary full" href="/api/auth/github/start">
              <Github size={18} /> Continue with GitHub OAuth
            </a>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                await post("/auth/pat", { token });
                setToken("");
                await refreshSession();
                await refreshJobs();
                setAuth(false);
              });
            }}
          >
            <label>
              Personal access token
              <input
                autoFocus
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="github_pat_…"
                required
              />
            </label>
            <button className="primary full" disabled={busy || !token}>
              {busy ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <Github size={17} />
              )}{" "}
              Connect securely
            </button>
          </form>
          <p className="form-note">
            Public repositories can be analyzed without signing in.
          </p>
        </Modal>
      )}
    </div>
  );
}

function Configure({
  repository,
  session,
  busy,
  onBack,
  onSubmit,
  onError,
}: {
  repository: Repository;
  session: Session;
  busy: boolean;
  onBack: () => void;
  onSubmit: (config: unknown) => void;
  onError: (message: string) => void;
}) {
  const [ref, setRef] = useState(repository.default_branch);
  const [refs, setRefs] = useState<string[]>([]);
  const [depth, setDepth] = useState("standard");
  const [documents, setDocuments] = useState<DocKind[]>(DOCS.map((d) => d.id));
  const [formats, setFormats] = useState(["md", "docx"]);
  const [provider, setProvider] = useState<Provider | "">("");
  const [model, setModel] = useState("");
  const [fallback, setFallback] = useState<Provider | "">("");
  const [fallbackModel, setFallbackModel] = useState("");
  const [consent, setConsent] = useState(false);
  const [tests, setTests] = useState(false);
  const [profile, setProfile] = useState("pytest");
  useEffect(() => {
    api<{ items: { name: string }[] }>(
      `/repositories/${repository.full_name}/refs`,
    )
      .then((r) => setRefs(r.items.map((i) => i.name)))
      .catch((e) => onError(e.message));
  }, [repository.full_name]);
  const toggleDoc = (id: DocKind) =>
    setDocuments((old) =>
      old.includes(id) ? old.filter((i) => i !== id) : [...old, id],
    );
  const providers = provider
    ? [
        { provider, model },
        ...(fallback ? [{ provider: fallback, model: fallbackModel }] : []),
      ]
    : [];
  return (
    <div className="configuration">
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={16} /> All repositories
      </button>
      <div className="section-heading">
        <div>
          <div className="eyebrow">NEW ANALYSIS</div>
          <h1>Make the code speak.</h1>
          <p>Choose the scope and documentation your team needs.</p>
        </div>
        <Badge tone="green">
          <ShieldCheck size={12} /> Read-only analysis
        </Badge>
      </div>
      <div className="stepper">
        <span>
          <Check size={14} /> Select repository
        </span>
        <i />
        <span className="current">
          2 <strong>Configure analysis</strong>
        </span>
        <i />
        <span>3 Review documentation</span>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit({
            repository: repository.full_name,
            ref,
            depth,
            documents,
            formats,
            providers,
            consent_providers: consent ? providers.map((p) => p.provider) : [],
            execute_tests: tests,
            test_profile: profile,
          });
        }}
      >
        <div className="config-layout">
          <div>
            <section className="panel">
              <div className="panel-heading">
                <GitBranch size={20} />
                <h2>Source & scope</h2>
              </div>
              <div className="selected-repo">
                <FolderGit2 size={25} />
                <div>
                  <strong>{repository.full_name}</strong>
                  <a href={repository.url} target="_blank" rel="noreferrer">
                    View on GitHub ↗
                  </a>
                </div>
                <Badge>{repository.private ? "Private" : "Public"}</Badge>
              </div>
              <label>
                Branch, tag or commit
                <input
                  list="git-refs"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  required
                />
                <datalist id="git-refs">
                  {refs.map((r) => (
                    <option key={r} value={r} />
                  ))}
                </datalist>
                <small>
                  Resolved to a fixed commit before analysis begins.
                </small>
              </label>
              <label>Analysis depth</label>
              <div className="segmented">
                {["basic", "standard", "comprehensive"].map((d) => (
                  <button
                    type="button"
                    key={d}
                    className={depth === d ? "selected" : ""}
                    onClick={() => setDepth(d)}
                  >
                    {d}
                    {d === "standard" && <small>Recommended</small>}
                  </button>
                ))}
              </div>
              <p className="form-note">
                {depth === "basic"
                  ? "Up to 400 files and 2 AI batches."
                  : depth === "standard"
                    ? "Up to 3,000 files and 10 AI batches."
                    : "Up to 15,000 files and 40 AI batches."}{" "}
                Analysis limits and omissions are recorded in the report.
              </p>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <FileText size={20} />
                <h2>Documentation deliverables</h2>
                <button
                  type="button"
                  className="text-button"
                  onClick={() =>
                    setDocuments(
                      documents.length === 7 ? [] : DOCS.map((d) => d.id),
                    )
                  }
                >
                  {documents.length === 7 ? "Clear all" : "Select all"}
                </button>
              </div>
              <div className="doc-options">
                {DOCS.map((d) => (
                  <label
                    className={`doc-option ${documents.includes(d.id) ? "chosen" : ""}`}
                    key={d.id}
                  >
                    <input
                      type="checkbox"
                      checked={documents.includes(d.id)}
                      onChange={() => toggleDoc(d.id)}
                    />
                    <d.icon size={20} />
                    <span>
                      <strong>{d.title}</strong>
                      <small>{d.description}</small>
                    </span>
                  </label>
                ))}
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <Sparkles size={20} />
                <h2>AI synthesis</h2>
              </div>
              <div className="form-columns">
                <label>
                  Provider
                  <select
                    value={provider}
                    onChange={(e) => {
                      const p = e.target.value as Provider | "";
                      setProvider(p);
                      setFallback("");
                      setModel(
                        session.providers.find((x) => x.id === p)?.model || "",
                      );
                      setConsent(false);
                    }}
                  >
                    <option value="">Static analysis only</option>
                    {session.providers.map((p) => (
                      <option key={p.id} value={p.id} disabled={!p.configured}>
                        {providerNames[p.id]}
                        {!p.configured ? " · key not configured" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {provider && (
                  <label>
                    Model
                    <input
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder="Model ID available in your account"
                      required
                    />
                  </label>
                )}
              </div>
              {provider && (
                <>
                  <div className="form-columns">
                    <label>
                      Fallback provider
                      <select
                        value={fallback}
                        onChange={(e) => {
                          const p = e.target.value as Provider | "";
                          setFallback(p);
                          setFallbackModel(
                            session.providers.find((x) => x.id === p)?.model ||
                              "",
                          );
                          setConsent(false);
                        }}
                      >
                        <option value="">No fallback</option>
                        {session.providers
                          .filter((p) => p.id !== provider)
                          .map((p) => (
                            <option
                              key={p.id}
                              value={p.id}
                              disabled={!p.configured}
                            >
                              {providerNames[p.id]}
                            </option>
                          ))}
                      </select>
                    </label>
                    {fallback && (
                      <label>
                        Fallback model
                        <input
                          value={fallbackModel}
                          onChange={(e) => setFallbackModel(e.target.value)}
                          required
                        />
                      </label>
                    )}
                  </div>
                  <label className="checkbox-note">
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                      required={repository.private}
                    />
                    <span>
                      I authorize sending redacted repository evidence to{" "}
                      {providers
                        .map((p) => providerNames[p.provider])
                        .join(" and ")}
                      . Automatic fallback is limited to these providers.
                    </span>
                  </label>
                </>
              )}
              <p className="form-note">
                AI conclusions remain inferred until reviewed. Secret redaction
                reduces exposure, but cannot guarantee detection of every
                proprietary value.
              </p>
            </section>
          </div>
          <aside className="config-summary">
            <section className="panel">
              <div className="panel-heading">
                <Settings2 size={20} />
                <h2>Output settings</h2>
              </div>
              <label>Download formats</label>
              <div className="format-options">
                {["md", "docx", "pdf"].map((f) => (
                  <label key={f}>
                    <input
                      type="checkbox"
                      checked={formats.includes(f)}
                      onChange={() =>
                        setFormats((old) =>
                          old.includes(f)
                            ? old.filter((x) => x !== f)
                            : [...old, f],
                        )
                      }
                    />
                    {f.toUpperCase()}
                  </label>
                ))}
              </div>
              <p className="form-note">
                Markdown previews, evidence JSON and diagrams accompany selected
                exports. Testing documents include an XLSX traceability matrix.
              </p>
              <div className="summary-divider" />
              <label className="checkbox-note">
                <input
                  type="checkbox"
                  checked={tests}
                  disabled={!session.test_execution_enabled}
                  onChange={(e) => setTests(e.target.checked)}
                />
                <span>Run existing repository tests</span>
              </label>
              <p className="form-note">
                {session.test_execution_enabled
                  ? "Executes in a restricted, network-disabled container with a trusted image."
                  : "Disabled until an administrator configures an isolated test worker."}
              </p>
              {tests && (
                <label>
                  Test profile
                  <select
                    value={profile}
                    onChange={(e) => setProfile(e.target.value)}
                  >
                    <option value="pytest">Pytest</option>
                    <option value="npm">npm test</option>
                  </select>
                </label>
              )}
              <div className="summary-divider" />
              <div className="summary-row">
                <span>Deliverables</span>
                <strong>{documents.length} selected</strong>
              </div>
              <div className="summary-row">
                <span>Source mode</span>
                <strong>Read only</strong>
              </div>
              <button
                className="primary full"
                disabled={busy || !documents.length || !formats.length}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Sparkles size={16} />
                )}{" "}
                Generate documentation
              </button>
              <p className="form-note center">
                Formal approval always stays with your team.
              </p>
            </section>
          </aside>
        </div>
      </form>
    </div>
  );
}

function Report({
  job,
  session,
  onRefresh,
  onError,
  onBack,
}: {
  job: Job;
  session: Session | null;
  onRefresh: () => Promise<void>;
  onError: (message: string) => void;
  onBack: () => void;
}) {
  const [tab, setTab] = useState("overview");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{ name: string; text: string } | null>(
    null,
  );
  const [edit, setEdit] = useState<Requirement | null>(null);
  const [test, setTest] = useState<Case | null>(null);
  const [review, setReview] = useState(false);
  const [audit, setAudit] = useState<
    {
      id: number;
      actor: string;
      action: string;
      detail: Record<string, unknown>;
      created: string;
    }[]
  >([]);
  const analysis = job.analysis;
  const state = job.workflow;
  const evidence = useMemo(
    () => new Map(analysis?.evidence.map((e) => [e.id, e]) || []),
    [analysis],
  );
  useEffect(() => {
    if (job.status === "completed") {
      api<{ files: Artifact[] }>(`/jobs/${job.id}/files`)
        .then((r) => setArtifacts(r.files))
        .catch((e) => onError(e.message));
      api<typeof audit>(`/jobs/${job.id}/audit`)
        .then(setAudit)
        .catch((e) => onError(e.message));
    }
  }, [job.id, job.version, job.status]);
  const download = (path = "", version = job.version) =>
    `/api/jobs/${job.id}/download?${new URLSearchParams({ path, version: String(version) })}`;
  async function mutate(path: string, body: unknown, method = "POST") {
    try {
      await api(`/jobs/${job.id}/${path}`, {
        method,
        body: JSON.stringify(body),
      });
      await onRefresh();
      return true;
    } catch (e) {
      onError((e as Error).message);
      return false;
    }
  }
  if (job.status !== "completed" || !analysis || !state)
    return (
      <div>
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={16} /> Workspace
        </button>
        <div className="progress-card">
          <span className="progress-icon">
            {job.status === "failed" ? (
              <CircleHelp size={32} />
            ) : (
              <Sparkles size={32} />
            )}
          </span>
          <div className="eyebrow">{job.repository}</div>
          <h1>
            {job.status === "failed"
              ? "Analysis needs attention"
              : "Reading between the lines."}
          </h1>
          <p>{job.message}</p>
          <div className="progress-track">
            <span style={{ width: `${job.progress}%` }} />
          </div>
          <div className="progress-label">
            <span>
              {job.status === "failed" ? "Stopped" : "Analysis in progress"}
            </span>
            <strong>{job.progress}%</strong>
          </div>
          <p className="form-note">
            Source retrieval → static evidence → requirements → documentation
          </p>
        </div>
      </div>
    );
  const matchingRequirements = analysis.requirements.filter((r) =>
    `${r.id} ${r.title} ${r.module}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const matchingTests = analysis.test_cases.filter((t) =>
    `${t.id} ${t.title} ${t.requirement_id}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const resultMap = new Map(state.results.map((r) => [r.test_case_id, r]));
  return (
    <div className="report">
      <button className="back-button" onClick={onBack}>
        <ArrowLeft size={16} /> Workspace
      </button>
      <div className="report-heading">
        <div>
          <div className="eyebrow">DOCUMENTATION WORKSPACE</div>
          <h1>{job.repository.split("/")[1]}</h1>
          <div className="report-meta">
            <span>{job.repository}</span>
            <span>
              <GitBranch size={13} /> {analysis.commit.slice(0, 10)}
            </span>
            <Badge>Version {job.version}</Badge>
          </div>
        </div>
        <div className="report-actions">
          <button className="secondary" onClick={() => setReview(true)}>
            <CheckCheck size={16} /> Review baseline
          </button>
          <a className="primary" href={download()}>
            <ArrowDownToLine size={16} /> Download package
          </a>
        </div>
      </div>
      <div className="review-strip">
        <ShieldCheck size={17} />
        <span>
          Requirements{" "}
          <Badge
            tone={state.requirements_status === "approved" ? "green" : "amber"}
          >
            {human(state.requirements_status)}
          </Badge>
        </span>
        <span>
          Application acceptance{" "}
          <Badge tone={state.uat_status === "approved" ? "green" : "amber"}>
            {human(state.uat_status)}
          </Badge>
        </span>
        <small>Approvals are controlled by authorized reviewers.</small>
      </div>
      <div className="tabs" role="tablist">
        {[
          "overview",
          "requirements",
          "tests",
          "documents",
          "diagrams",
          "activity",
          ...(job.is_owner ? ["access"] : []),
        ].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => {
              setTab(t);
              setQuery("");
            }}
          >
            {t}
            {t === "requirements" && (
              <span>{analysis.requirements.length}</span>
            )}
            {t === "tests" && <span>{analysis.test_cases.length}</span>}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <>
          <div className="report-stats">
            {[
              [analysis.stats.scanned_files, "Files inspected"],
              [analysis.requirements.length, "Requirement candidates"],
              [state.counts.unexecuted, "Unexecuted test cases"],
              [analysis.stats.reused_files, "Files reused from cache"],
            ].map(([value, caption]) => (
              <div key={caption}>
                <strong>{value}</strong>
                <span>{caption}</span>
              </div>
            ))}
          </div>
          <div className="report-columns">
            <section className="panel">
              <div className="panel-heading">
                <Layers3 size={19} />
                <h2>Detected technologies</h2>
              </div>
              <div className="tech-tags">
                {[
                  ...new Set(
                    analysis.findings
                      .filter((f) => f.kind === "technology")
                      .map((f) => f.title),
                  ),
                ].map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
              <div className="summary-divider" />
              <h3>Repository composition</h3>
              {Object.entries(analysis.stats.languages).map(
                ([language, count]) => (
                  <div className="language-row" key={language}>
                    <span>{language}</span>
                    <div>
                      <span
                        style={{
                          width: `${(count / analysis.stats.scanned_files) * 100}%`,
                        }}
                      />
                    </div>
                    <strong>{count}</strong>
                  </div>
                ),
              )}
              {analysis.changes && (
                <>
                  <div className="summary-divider" />
                  <h3>
                    Changes since {analysis.changes.previous_commit.slice(0, 8)}
                  </h3>
                  <p className="muted">
                    {analysis.changes.added.length} added ·{" "}
                    {analysis.changes.modified.length} modified ·{" "}
                    {analysis.changes.removed.length} removed
                  </p>
                </>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <CircleHelp size={19} />
                <h2>Items for human review</h2>
              </div>
              <p className="muted">
                These limits and clarifications are included in your
                documentation.
              </p>
              <div className="gaps-list">
                {analysis.gaps.map((gap, i) => (
                  <p key={i}>
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    {gap}
                  </p>
                ))}
              </div>
            </section>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <Sparkles size={19} />
              <h2>AI usage & execution evidence</h2>
            </div>
            {analysis.usage.length ? (
              <p>
                {analysis.usage.filter((u) => u.status === "completed").length}{" "}
                successful requests ·{" "}
                {analysis.usage
                  .reduce(
                    (s, u) =>
                      s + (u.input_tokens || 0) + (u.output_tokens || 0),
                    0,
                  )
                  .toLocaleString()}{" "}
                reported tokens. Failed-request usage may be unavailable.
              </p>
            ) : (
              <p className="muted">
                Static analysis only. No repository evidence was sent to an AI
                provider.
              </p>
            )}
            {analysis.execution ? (
              <pre className="code-block">
                {JSON.stringify(analysis.execution, null, 2)}
              </pre>
            ) : (
              <p className="form-note">
                Repository tests were not executed. Generated test cases remain
                unexecuted until verified results are recorded.
              </p>
            )}
          </section>
        </>
      )}
      {(tab === "requirements" || tab === "tests") && (
        <>
          <div className="results-toolbar">
            <div className="input-icon">
              <Search size={17} />
              <input
                placeholder={`Search ${tab}, IDs or modules…`}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label={`Search ${tab}`}
              />
            </div>
            <span className="muted">
              {tab === "requirements"
                ? matchingRequirements.length
                : matchingTests.length}{" "}
              records
            </span>
          </div>
          {tab === "requirements"
            ? matchingRequirements.slice(0, 100).map((r) => (
                <article className="requirement-card" key={r.id}>
                  <div className="record-heading">
                    <code>{r.id}</code>
                    <Badge tone="amber">{r.confidence}</Badge>
                    {job.can_review && (
                      <button
                        className="text-button"
                        onClick={() => setEdit(r)}
                      >
                        Edit requirement
                      </button>
                    )}
                  </div>
                  <h3>{r.title}</h3>
                  <p>{r.statement}</p>
                  <div className="record-meta">
                    <FileCode2 size={14} /> {r.module}
                    <span>Source: {r.source}</span>
                  </div>
                  <EvidenceList ids={r.evidence_ids} evidence={evidence} />
                </article>
              ))
            : matchingTests.slice(0, 100).map((t) => {
                const result = resultMap.get(t.id);
                return (
                  <article className="requirement-card" key={t.id}>
                    <div className="record-heading">
                      <code>{t.id}</code>
                      <Badge
                        tone={result?.status === "passed" ? "green" : "amber"}
                      >
                        {result?.status || "unexecuted"}
                      </Badge>
                      <Badge>{t.category}</Badge>
                    </div>
                    <h3>{t.title}</h3>
                    <small className="muted">
                      Requirement {t.requirement_id}
                    </small>
                    <details>
                      <summary>
                        Scenario and expected outcome <ChevronDown size={14} />
                      </summary>
                      <h4>Preconditions</h4>
                      {t.preconditions.map((p) => (
                        <p key={p}>{p}</p>
                      ))}
                      <h4>Steps</h4>
                      <ol>
                        {t.steps.map((p) => (
                          <li key={p}>{p}</li>
                        ))}
                      </ol>
                      <h4>Expected result</h4>
                      <p>{t.expected}</p>
                      {result && (
                        <>
                          <h4>Recorded result</h4>
                          <p>{result.actual}</p>
                          <p className="muted">
                            {result.source} · {result.reviewer} ·{" "}
                            {result.evidence_reference}
                          </p>
                        </>
                      )}
                    </details>
                    {job.can_review && (
                      <button
                        className="text-button"
                        onClick={() => setTest(t)}
                      >
                        Record verified result <ArrowRight size={14} />
                      </button>
                    )}
                  </article>
                );
              })}
          {(tab === "requirements"
            ? matchingRequirements.length
            : matchingTests.length) > 100 && (
            <p className="form-note">
              Showing the first 100 matches. Narrow the search or download the
              complete package.
            </p>
          )}
        </>
      )}
      {tab === "documents" && (
        <>
          <div className="section-heading">
            <div>
              <h2>Your documentation package</h2>
              <p>Preview Markdown or download individual artifacts.</p>
            </div>
            <select
              aria-label="Download earlier version"
              defaultValue=""
              onChange={(e) => {
                if (e.target.value)
                  window.location.href = download("", Number(e.target.value));
              }}
            >
              <option value="">Version history</option>
              {[...(job.versions || [job.version])].reverse().map((v) => (
                <option key={v} value={v}>
                  Download version {v}
                </option>
              ))}
            </select>
          </div>
          <div className="artifact-list">
            {artifacts.map((file) => (
              <div key={file.path}>
                <span className="file-icon">
                  <FileText size={20} />
                </span>
                <div>
                  <strong>
                    {file.path.split("/").pop()?.replaceAll("_", " ")}
                  </strong>
                  <small>
                    {file.path.split("/")[0]} · {(file.bytes / 1024).toFixed(1)}{" "}
                    KB
                  </small>
                </div>
                {file.path.endsWith(".md") && (
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        const r = await api<{ content: string }>(
                          `/jobs/${job.id}/preview?path=${encodeURIComponent(file.path)}`,
                        );
                        setPreview({
                          name: file.path.split("/").pop()!,
                          text: r.content,
                        });
                      } catch (e) {
                        onError((e as Error).message);
                      }
                    }}
                  >
                    Preview
                  </button>
                )}
                <a
                  className="icon-button"
                  href={download(file.path)}
                  aria-label={`Download ${file.path}`}
                >
                  <ArrowDownToLine size={17} />
                </a>
              </div>
            ))}
          </div>
        </>
      )}
      {tab === "diagrams" && (
        <div className="diagram-grid">
          {artifacts
            .filter((a) => a.path.endsWith(".svg"))
            .map((a) => (
              <section className="panel" key={a.path}>
                <div className="panel-heading">
                  <Network size={18} />
                  <h2>
                    {a.path
                      .split("/")
                      .pop()
                      ?.replace(".svg", "")
                      .replaceAll("_", " ")}
                  </h2>
                  <a href={download(a.path)} aria-label="Download diagram">
                    <ArrowDownToLine size={17} />
                  </a>
                </div>
                <img src={download(a.path)} alt={a.path.split("/").pop()} />
                <p className="form-note">
                  Connections are labelled by observed evidence. Inferred actors
                  and incomplete data flows require review.
                </p>
              </section>
            ))}
        </div>
      )}
      {tab === "activity" && (
        <section className="panel">
          <div className="panel-heading">
            <CheckCheck size={20} />
            <h2>Version and review history</h2>
          </div>
          {audit.map((a) => (
            <div className="audit-row" key={a.id}>
              <span className="audit-dot" />
              <div>
                <strong>{human(a.action)}</strong>
                <p>
                  {a.actor} · {time(a.created)}
                </p>
                <code>{JSON.stringify(a.detail)}</code>
              </div>
            </div>
          ))}
          {state.reviews.map((r) => (
            <div className="review-comment" key={r.id}>
              <Badge>
                {r.current ? "Current baseline" : "Earlier baseline"}
              </Badge>
              <strong>
                {r.reviewer}: {human(r.decision)}
              </strong>
              <p>{r.comment}</p>
            </div>
          ))}
        </section>
      )}
      {tab === "access" && (
        <AccessPanel job={job} connected={!!session?.login} onError={onError} />
      )}
      {preview && (
        <Modal
          wide
          title={preview.name.replaceAll("_", " ")}
          onClose={() => setPreview(null)}
        >
          <div className="markdown-preview">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {preview.text}
            </ReactMarkdown>
          </div>
        </Modal>
      )}
      {review && (
        <ReviewModal
          job={job}
          canReview={!!job.can_review}
          onClose={() => setReview(false)}
          onSave={async (body) => {
            if (await mutate("reviews", body)) setReview(false);
          }}
        />
      )}
      {edit && (
        <EditModal
          requirement={edit}
          onClose={() => setEdit(null)}
          onSave={async (statement, rationale) => {
            if (
              await mutate(
                `requirements/${edit.id}`,
                { statement, rationale, baseline_hash: job.baseline_hash },
                "PATCH",
              )
            )
              setEdit(null);
          }}
        />
      )}
      {test && (
        <ResultModal
          test={test}
          baselineHash={job.baseline_hash}
          onClose={() => setTest(null)}
          onSave={async (body) => {
            if (await mutate("results", body)) setTest(null);
          }}
        />
      )}
    </div>
  );
}

function AccessPanel({
  job,
  connected,
  onError,
}: {
  job: Job;
  connected: boolean;
  onError: (message: string) => void;
}) {
  const [members, setMembers] = useState<{ login: string; role: string }[]>([]);
  const [login, setLogin] = useState("");
  const [role, setRole] = useState("viewer");
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  const refresh = () =>
    api<typeof members>(`/jobs/${job.id}/collaborators`).then(setMembers);
  useEffect(() => {
    refresh().catch((e) => onError(e.message));
  }, [job.id]);
  return (
    <section className="panel">
      <div className="panel-heading">
        <LockKeyhole size={20} />
        <h2>Collaborator access</h2>
      </div>
      <p className="muted">
        Grant access to this analysis, its source evidence and all artifact
        versions. Reviewer access also requires the server's authorized reviewer
        list. Access is resolved to the verified GitHub account ID.
      </p>
      {!connected && (
        <div className="notice">
          Connect your GitHub account before sharing an analysis.
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          try {
            await post(`/jobs/${job.id}/collaborators`, {
              login,
              role,
              acknowledged: ack,
            });
            await refresh();
            setLogin("");
            setAck(false);
          } catch (e) {
            onError((e as Error).message);
          } finally {
            setSaving(false);
          }
        }}
      >
        <div className="form-columns">
          <label>
            GitHub username
            <input
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              pattern="[A-Za-z0-9][A-Za-z0-9-]{0,38}"
              required
            />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="viewer">View documents and evidence</option>
              <option value="reviewer">Review and record evidence</option>
            </select>
          </label>
        </div>
        <label className="checkbox-note">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            required
          />
          <span>
            I authorize sharing all documentation and source evidence in this
            analysis with this GitHub account.
          </span>
        </label>
        <button className="primary" disabled={saving || !connected}>
          {saving ? "Saving…" : "Grant access"}
        </button>
      </form>
      <div className="summary-divider" />
      {members.length ? (
        members.map((member) => (
          <div className="summary-row" key={member.login}>
            <span>
              {member.login} · {member.role}
            </span>
            <button
              className="text-button"
              onClick={async () => {
                try {
                  await api(`/jobs/${job.id}/collaborators/${member.login}`, {
                    method: "DELETE",
                  });
                  await refresh();
                } catch (e) {
                  onError((e as Error).message);
                }
              }}
            >
              Revoke access
            </button>
          </div>
        ))
      ) : (
        <p className="form-note">
          Only the analysis owner currently has access.
        </p>
      )}
    </section>
  );
}

function EvidenceList({
  ids,
  evidence,
}: {
  ids: string[];
  evidence: Map<string, Evidence>;
}) {
  return (
    <details className="evidence-details">
      <summary>
        <Code2 size={14} /> Source evidence <Badge>{ids.length}</Badge>
        <ChevronDown size={13} />
      </summary>
      {ids.map((id) => {
        const e = evidence.get(id);
        return e ? (
          <div key={id}>
            <p>
              <code>{e.id}</code> · {e.path}:{e.start_line}–{e.end_line}
            </p>
            <pre className="code-block">{e.snippet}</pre>
          </div>
        ) : null;
      })}
    </details>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={19} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function ReviewModal({
  job,
  canReview,
  onClose,
  onSave,
}: {
  job: Job;
  canReview: boolean;
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const [stage, setStage] = useState("requirements");
  const [decision, setDecision] = useState("comment");
  const [comment, setComment] = useState("");
  const [ack, setAck] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="Record a human review" onClose={onClose}>
      <p className="muted">
        Your decision is bound to the current requirements or UAT evidence
        baseline. Later changes invalidate earlier acceptance.
      </p>
      {!canReview && (
        <div className="notice">
          Sign in with a GitHub account included in the administrator’s reviewer
          list to record decisions.
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave({
            stage,
            decision,
            comment,
            acknowledged: ack,
            baseline_hash:
              stage === "requirements"
                ? job.baseline_hash
                : job.workflow?.acceptance_hash,
          });
          setSaving(false);
        }}
      >
        <label>
          Review stage
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="requirements">Requirements baseline</option>
            <option value="uat">Application / UAT acceptance</option>
          </select>
        </label>
        <label>
          Decision
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value)}
          >
            <option value="comment">Comment only</option>
            <option value="changes_requested">Request changes</option>
            <option
              value="approved"
              disabled={stage === "uat" && !job.workflow?.ready_for_acceptance}
            >
              Approve this baseline
            </option>
          </select>
        </label>
        {stage === "uat" && !job.workflow?.ready_for_acceptance && (
          <p className="form-note">
            Acceptance is pending requirements approval and passing evidence for
            every test case.
          </p>
        )}
        <label>
          Review comment
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            required
            rows={4}
          />
        </label>
        {decision === "approved" && (
          <label className="checkbox-note">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              required
            />
            <span>
              I have reviewed this baseline and am authorized to record this
              approval.
            </span>
          </label>
        )}
        <button className="primary full" disabled={!canReview || saving}>
          {saving ? "Saving…" : "Record review"}
        </button>
      </form>
    </Modal>
  );
}
function EditModal({
  requirement,
  onClose,
  onSave,
}: {
  requirement: Requirement;
  onClose: () => void;
  onSave: (s: string, r: string) => Promise<void>;
}) {
  const [statement, setStatement] = useState(requirement.statement);
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <Modal title={`Edit ${requirement.id}`} onClose={onClose}>
      <p className="muted">
        This creates a new baseline. Earlier approvals and test results remain
        in history and will need revalidation.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave(statement, rationale);
          setSaving(false);
        }}
      >
        <label>
          Requirement statement
          <textarea
            rows={6}
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            minLength={10}
            required
          />
        </label>
        <label>
          Reason for change
          <textarea
            rows={3}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            minLength={5}
            required
          />
        </label>
        <button className="primary full" disabled={saving}>
          {saving ? "Saving…" : "Save a new baseline"}
        </button>
      </form>
    </Modal>
  );
}
function ResultModal({
  test,
  baselineHash,
  onClose,
  onSave,
}: {
  test: Case;
  baselineHash: string;
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const [status, setStatus] = useState("blocked");
  const [source, setSource] = useState("manual_uat");
  const [actual, setActual] = useState("");
  const [reference, setReference] = useState("");
  const [severity, setSeverity] = useState("none");
  const [attested, setAttested] = useState(false);
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="Record a verified test result" onClose={onClose}>
      <p className="muted">
        {test.id} · {test.title}
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          await onSave({
            test_case_id: test.id,
            status,
            source,
            actual,
            evidence_reference: reference,
            severity,
            attested,
            baseline_hash: baselineHash,
          });
          setSaving(false);
        }}
      >
        <div className="form-columns">
          <label>
            Result
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="blocked">Blocked</option>
              <option value="failed">Failed</option>
              <option value="passed">Passed</option>
            </select>
          </label>
          <label>
            Evidence type
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="manual_uat">Manual UAT</option>
              <option value="existing_report">Verified existing report</option>
            </select>
          </label>
        </div>
        <label>
          Actual outcome
          <textarea
            value={actual}
            onChange={(e) => setActual(e.target.value)}
            minLength={10}
            rows={4}
            required
          />
        </label>
        <label>
          Evidence URL or report reference
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            minLength={5}
            required
          />
        </label>
        <label>
          Defect severity
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            {["none", "low", "medium", "high", "critical"].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="checkbox-note">
          <input
            type="checkbox"
            checked={attested}
            onChange={(e) => setAttested(e.target.checked)}
            required
          />
          <span>
            I verified this evidence against the selected test case and analyzed
            commit.
          </span>
        </label>
        <button className="primary full" disabled={saving}>
          {saving ? "Saving…" : "Record verified result"}
        </button>
      </form>
    </Modal>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
