import { describe, expect, it } from "vitest";
import { repositoryName } from "./api";

describe("repository input", () => {
  it("normalizes a GitHub URL without accepting another host", () => {
    expect(repositoryName(" https://github.com/team/project.git ")).toBe(
      "team/project",
    );
    expect(repositoryName("team/project/")).toBe("team/project");
    expect(repositoryName("https://attacker.test/team/project")).toBe(
      "https://attacker.test/team/project",
    );
  });
});
