export type Provider = "openai" | "anthropic" | "gemini";
export type DocKind =
  | "srs"
  | "requirements_signoff"
  | "test_cases"
  | "uat_signoff"
  | "data_flow"
  | "architecture"
  | "technology";
export interface Session {
  login: string | null;
  csrf_token: string;
  can_review: boolean;
  oauth_enabled: boolean;
  test_execution_enabled: boolean;
  providers: { id: Provider; configured: boolean; model: string }[];
}
export interface Repository {
  name: string;
  owner: string;
  full_name: string;
  private: boolean;
  description: string;
  default_branch: string;
  language: string | null;
  updated_at: string;
  url: string;
}
export interface Evidence {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  symbol: string;
  snippet: string;
  commit: string;
}
export interface Requirement {
  id: string;
  title: string;
  statement: string;
  confidence: string;
  evidence_ids: string[];
  module: string;
  source: string;
}
export interface Case {
  id: string;
  requirement_id: string;
  title: string;
  category: string;
  preconditions: string[];
  steps: string[];
  expected: string;
}
export interface Finding {
  id: string;
  kind: string;
  title: string;
  detail: string;
  confidence: string;
  evidence_ids: string[];
  metadata: Record<string, string>;
}
export interface TestResult {
  test_case_id: string;
  status: string;
  source: string;
  actual: string;
  reviewer: string;
  evidence_reference: string;
}
export interface Workflow {
  requirements_status: string;
  uat_status: string;
  acceptance_hash: string;
  ready_for_acceptance: boolean;
  counts: Record<string, number>;
  results: TestResult[];
  reviews: {
    id: number;
    stage: string;
    decision: string;
    reviewer: string;
    comment: string;
    current: boolean;
    created: string;
  }[];
}
export interface Analysis {
  commit: string;
  repository: string;
  private: boolean;
  evidence: Evidence[];
  findings: Finding[];
  requirements: Requirement[];
  test_cases: Case[];
  gaps: string[];
  inventory: { path: string; category: string; language: string }[];
  stats: {
    scanned_files: number;
    reused_files: number;
    languages: Record<string, number>;
  };
  usage: {
    provider: string;
    model: string;
    status: string;
    input_tokens?: number;
    output_tokens?: number;
  }[];
  execution: Record<string, unknown> | null;
  changes?: {
    added: string[];
    removed: string[];
    modified: string[];
    previous_commit: string;
  };
}
export interface Job {
  versions?: number[];
  is_owner?: boolean;
  can_review?: boolean;
  id: string;
  repository: string;
  status: string;
  progress: number;
  message: string;
  version: number;
  baseline_hash: string;
  created: string;
  analysis?: Analysis;
  workflow?: Workflow;
}
export interface Artifact {
  path: string;
  bytes: number;
}
