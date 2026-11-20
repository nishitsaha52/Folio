import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Check,
  FileText,
  FolderGit2,
  GitBranch,
  LoaderCircle,
  Settings2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { DocKind, Provider, Repository, Session } from "../types";
import { api } from "../api";
import { DOCS, providerNames, Badge } from "./shared";

export function Configure({
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
    const controller = new AbortController();
    api<{ items: { name: string }[] }>(
      `/repositories/${repository.full_name}/refs`,
      { signal: controller.signal },
    )
      .then((r) => {
        if (!controller.signal.aborted) setRefs(r.items.map((i) => i.name));
      })
      .catch((e) => {
        if (!controller.signal.aborted) onError(e.message);
      });
    return () => controller.abort();
  }, [repository.full_name, onError]);
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
              <details className="form-note">
                <summary>Which files are included?</summary>
                <p>
                  Folio inspects source code, tests and project configuration.
                  Dependency folders, caches, build directories and
                  fingerprinted or minified browser bundles are excluded
                  automatically.
                </p>
                <p>
                  Review the Scan coverage section after analysis for excluded
                  paths, reasons and suggested .docagentignore rules. Keep
                  original frontend source included. Use !path/to/file.js to
                  override an automatic generated-file exclusion.
                </p>
              </details>
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
