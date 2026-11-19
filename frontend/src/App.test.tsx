import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { repository, session } from "./test/fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("GitHub connection", () => {
  it("rotates CSRF credentials after PAT login and clears the account on logout", async () => {
    let authenticated = false;
    const fetchMock = vi.fn(async (path: string, options?: RequestInit) => {
      const headers = options?.headers as Record<string, string>;
      let body: unknown;
      if (path === "/api/session") {
        body = {
          ...session,
          login: authenticated ? "reviewer" : null,
          csrf_token: authenticated ? "rotated-csrf" : "anonymous-csrf",
        };
      } else if (path === "/api/auth/pat") {
        expect(headers["X-CSRF-Token"]).toBe("anonymous-csrf");
        expect(JSON.parse(options?.body as string)).toEqual({
          token: "github_pat_test_token",
        });
        authenticated = true;
        body = { login: "reviewer" };
      } else if (path === "/api/auth/logout") {
        expect(headers["X-CSRF-Token"]).toBe("rotated-csrf");
        authenticated = false;
        body = { status: "disconnected" };
      } else if (path === "/api/jobs") {
        body = [];
      } else if (path.startsWith("/api/repositories?")) {
        body = { items: [], has_next: false };
      } else {
        throw new Error(`Unexpected request: ${path}`);
      }
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/jobs", expect.anything()),
    );
    await user.click(screen.getByRole("button", { name: "Connect GitHub" }));
    const dialog = within(screen.getByRole("dialog"));
    await user.type(
      dialog.getByLabelText("Personal access token"),
      "github_pat_test_token",
    );
    await user.click(dialog.getByRole("button", { name: "Connect securely" }));
    await screen.findByText("GitHub connected");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /reviewer Authenticated workspace/ }),
    );
    await screen.findByText("Local workspace");
    expect(
      screen.queryByText("Authenticated workspace"),
    ).not.toBeInTheDocument();
  });
});

describe("workspace navigation", () => {
  it("preserves repository filters when returning from configuration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        let body: unknown;
        if (path === "/api/session") body = session;
        else if (path === "/api/jobs") body = [];
        else if (path.startsWith("/api/repositories?"))
          body = {
            items: [
              repository,
              {
                ...repository,
                name: "public-project",
                full_name: "team/public-project",
                private: false,
              },
            ],
            has_next: false,
          };
        else if (path.endsWith("/refs")) body = { items: [{ name: "main" }] };
        else throw new Error(`Unexpected request: ${path}`);
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "project" });
    await user.type(
      screen.getByRole("textbox", { name: "Search repositories" }),
      "project",
    );
    await user.selectOptions(screen.getByLabelText("Filter owner"), "team");
    await user.selectOptions(
      screen.getByLabelText("Filter visibility"),
      "private",
    );
    expect(
      screen.queryByRole("heading", { name: "public-project" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("heading", { name: "project" }));
    await screen.findByRole("heading", { name: "Make the code speak." });
    await user.click(screen.getByRole("button", { name: "All repositories" }));
    expect(
      screen.getByRole("textbox", { name: "Search repositories" }),
    ).toHaveValue("project");
    expect(screen.getByLabelText("Filter owner")).toHaveValue("team");
    expect(screen.getByLabelText("Filter visibility")).toHaveValue("private");
    expect(
      screen.queryByRole("heading", { name: "public-project" }),
    ).not.toBeInTheDocument();
  });

  it("opens a public repository URL and retains its input after navigating back", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      let body: unknown;
      if (path === "/api/session") body = { ...session, login: null };
      else if (path === "/api/jobs") body = [];
      else if (path === "/api/repositories/team/project")
        body = { ...repository, private: false };
      else if (path.endsWith("/refs")) body = { items: [] };
      else throw new Error(`Unexpected request: ${path}`);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    const open = screen.getByRole("button", { name: "Open repository" });
    await waitFor(() => expect(open).toBeEnabled());
    await user.type(
      screen.getByRole("textbox", { name: "GitHub repository URL" }),
      "https://github.com/team/project.git",
    );
    await user.click(open);
    await screen.findByRole("heading", { name: "Make the code speak." });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/repositories/team/project",
      expect.anything(),
    );
    await user.click(screen.getByRole("button", { name: "All repositories" }));
    expect(
      screen.getByRole("textbox", { name: "GitHub repository URL" }),
    ).toHaveValue("https://github.com/team/project.git");
  });
});
