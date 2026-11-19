# Frontend organization

`src/main.tsx` mounts the application. `src/App.tsx` coordinates the session, selected repository/job, navigation and mutations. It delegates rendering rather than implementing workspace sections or report tabs.

| Location under `frontend/src/` | Responsibility |
| --- | --- |
| `components/AppShell.tsx` | Sidebar, navigation, account action, top bar and error banner |
| `components/AuthDialog.tsx` | GitHub connection form; credentials remain controlled by App |
| `components/workspace/` | Introduction/statistics, repository picker and documentation deliverables |
| `components/Report.tsx` | Selected tab, shared record controls, review dialogs and baseline-bound mutations |
| `components/report/` | Overview, requirements, tests, documents, diagrams and activity tabs, plus report header, progress and shared record controls |
| `hooks/` | Repository discovery, job polling and artifact/audit loading |
| `styles/` | Base, workspace, configuration, report, modal and responsive styles |

Repository filters and URL input stay in App so leaving the workspace does not discard them. Report keeps search/pagination controls and review state; switching tabs resets the record controls. Document preview state belongs to the documents tab. The artifact-loading hook cancels requests and ignores old responses when a report changes.

Keep API mutations in the coordinators and pass intent callbacks to rendering components. Requirements edits, reviews and results must continue using the selected job's current baseline hashes. Generated tests remain unexecuted until evidence is recorded.

Run `npm run build` and `npm test` from `frontend/`. The interaction suite covers authentication, configuration, workspace navigation/filter persistence, polling, stale artifact responses, document previews, pagination and baseline-bound review/edit/result flows. The optional `scripts/ui_smoke.py` check exercises the real backend and desktop/mobile browser layouts.
