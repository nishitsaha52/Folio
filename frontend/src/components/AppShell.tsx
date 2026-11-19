import type { ReactNode } from "react";
import {
  BookOpen,
  ChevronRight,
  CircleHelp,
  FileText,
  Github,
  LayoutDashboard,
  LogOut,
  Plus,
  ShieldCheck,
  X,
} from "lucide-react";
import type { Job, Session } from "../types";
export type AppPage = "workspace" | "configure" | "report";
export function AppShell({
  page,
  jobs,
  completed,
  session,
  hasRepository,
  hasJob,
  error,
  onNavigate,
  onOpenJob,
  onAccount,
  onDismissError,
  children,
}: {
  page: AppPage;
  jobs: Job[];
  completed: number;
  session: Session | null;
  hasRepository: boolean;
  hasJob: boolean;
  error: string;
  onNavigate: (page: AppPage) => void;
  onOpenJob: (id: string) => void;
  onAccount: () => void;
  onDismissError: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => onNavigate("workspace")}>
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
            onClick={() => onNavigate("workspace")}
          >
            <LayoutDashboard size={18} /> Workspace
          </button>
          <button
            className={page === "configure" ? "active" : ""}
            onClick={() =>
              hasRepository ? onNavigate("configure") : onNavigate("workspace")
            }
          >
            <Plus size={18} /> New analysis
          </button>
          <button
            className={page === "report" ? "active" : ""}
            onClick={() =>
              hasJob ? onNavigate("report") : onNavigate("workspace")
            }
          >
            <FileText size={18} /> Documentation{" "}
            <span className="nav-count">{completed}</span>
          </button>
        </nav>
        <div className="sidebar-rule" />
        <div className="small-label">RECENT ANALYSES</div>
        <div className="recent-list">
          {jobs.slice(0, 5).map((j) => (
            <button key={j.id} onClick={() => onOpenJob(j.id)}>
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
          <button className="account" onClick={onAccount}>
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
              <button onClick={onDismissError} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
