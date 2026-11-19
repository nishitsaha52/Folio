import type { Case, Job, Repository, Session } from "../types";

export const session: Session = {
  login: "reviewer",
  csrf_token: "csrf",
  can_review: true,
  oauth_enabled: true,
  test_execution_enabled: false,
  providers: [
    { id: "openai", configured: true, model: "primary-model" },
    { id: "anthropic", configured: true, model: "fallback-model" },
  ],
};
export const repository: Repository = {
  name: "project",
  owner: "team",
  full_name: "team/project",
  private: true,
  description: "Test repository",
  default_branch: "main",
  language: "Python",
  updated_at: "2026-11-19T00:00:00Z",
  url: "https://github.com/team/project",
};
export const job: Job = {
  id: "job-1",
  repository: "team/project",
  status: "completed",
  progress: 100,
  message: "Ready",
  version: 1,
  baseline_hash: "a".repeat(64),
  created: "2026-11-19T00:00:00Z",
  workflow: {
    requirements_status: "pending",
    uat_status: "pending",
    acceptance_hash: "b".repeat(64),
    ready_for_acceptance: false,
    counts: { passed: 0, unexecuted: 1 },
    results: [],
    reviews: [],
  },
};
export const testCase: Case = {
  id: "TC-1",
  requirement_id: "REQ-1",
  title: "Validate quantity",
  category: "positive",
  preconditions: ["Prepare fixture"],
  steps: ["Submit quantity 1"],
  expected: "Item created",
};
