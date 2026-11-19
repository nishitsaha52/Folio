import {
  ArrowRight,
  FolderGit2,
  GitBranch,
  Github,
  LoaderCircle,
  LockKeyhole,
  Search,
} from "lucide-react";
import type { Repository, Session } from "../../types";
import { Badge } from "../shared";

export interface RepositoryFilters {
  search: string;
  owner: string;
  visibility: string;
  publicRepo: string;
}
export function RepositoryPicker({
  repos,
  session,
  busy,
  repoLoading,
  filters,
  onFiltersChange,
  onConnect,
  onChoose,
  onOpen,
}: {
  repos: Repository[];
  session: Session | null;
  busy: boolean;
  repoLoading: boolean;
  filters: RepositoryFilters;
  onFiltersChange: (filters: RepositoryFilters) => void;
  onConnect: () => void;
  onChoose: (repository: Repository) => void;
  onOpen: (value: string) => void;
}) {
  const { search, owner, visibility, publicRepo } = filters;
  const updateFilter = (key: keyof RepositoryFilters, value: string) =>
    onFiltersChange({ ...filters, [key]: value });
  const filtered = repos.filter(
    (r) =>
      (r.full_name + " " + r.description)
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (visibility === "all" || r.private === (visibility === "private")) &&
      (owner === "all" || r.owner === owner),
  );
  return (
    <section className="repository-section">
      <div className="section-heading">
        <div>
          <h2>Choose your repository</h2>
          <p>A good understanding starts at the source.</p>
        </div>
        {!session?.login && (
          <button className="secondary" onClick={() => onConnect()}>
            <Github size={17} /> Connect GitHub
          </button>
        )}
      </div>
      <form
        className="public-repo"
        onSubmit={(e) => {
          e.preventDefault();
          onOpen(publicRepo);
        }}
      >
        <div className="input-icon">
          <Github size={18} />
          <input
            id="repository-input"
            value={publicRepo}
            onChange={(e) => updateFilter("publicRepo", e.target.value)}
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
                onChange={(e) => updateFilter("search", e.target.value)}
                placeholder="Search repositories…"
                aria-label="Search repositories"
              />
            </div>
            <select
              value={owner}
              onChange={(e) => updateFilter("owner", e.target.value)}
              aria-label="Filter owner"
            >
              <option value="all">All owners</option>
              {[...new Set(repos.map((r) => r.owner))].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
            <select
              value={visibility}
              onChange={(e) => updateFilter("visibility", e.target.value)}
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
                onClick={() => onChoose(repo)}
              >
                <div className="repo-card-top">
                  <FolderGit2 size={23} />
                  <Badge>{repo.private ? "Private" : "Public"}</Badge>
                </div>
                <small>{repo.owner}</small>
                <h3>{repo.name}</h3>
                <p>
                  {repo.description || "No repository description provided."}
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
                  Updated {new Date(repo.updated_at).toLocaleDateString()}
                </small>
              </button>
            ))}
          </div>
          {repoLoading && (
            <div className="loading-line">
              <LoaderCircle className="spin" size={16} /> Discovering accessible
              repositories…
            </div>
          )}
          {!repoLoading && !filtered.length && (
            <div className="empty-state">
              No matching repositories. Try another filter or paste a repository
              URL.
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
            <br className="desktop-only" /> and those shared by your teams. Or
            open a public URL above.
          </p>
          <button className="text-button" onClick={() => onConnect()}>
            Connect your account <ArrowRight size={15} />
          </button>
          <div className="security-footnote">
            <LockKeyhole size={12} /> Credentials are encrypted. Your source
            repository stays unchanged.
          </div>
        </div>
      )}
    </section>
  );
}
