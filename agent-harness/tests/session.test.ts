import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { dirname } from "node:path";
import { describe, expect, it } from "vitest";
import { MemoryAuditSink } from "../src/audit.js";
import { createHarnessSession } from "../src/session.js";

describe("Pi session factory", () => {
  it("creates an in-memory session with only the allowlisted custom tool", async () => {
    const cwd = resolve(dirname(fileURLToPath(import.meta.url)), "..");
    const harness = await createHarnessSession({
      cwd,
      bridgeScript: resolve(cwd, "src/cs2_sim/agent_bridge.py"),
      skillDirs: [resolve(cwd, "skills")],
      allowedTools: ["simulate_round"],
    }, new MemoryAuditSink());
    try {
      const names = harness.session.agent.state.tools.map((tool) => tool.name);
      expect(names).toEqual(["simulate_round"]);
      expect(names).not.toContain("bash");
      expect(names).not.toContain("write");
    } finally {
      harness.dispose();
    }
  });

  it("exposes the replay pipeline only when it is explicitly allowlisted", async () => {
    const cwd = resolve(dirname(fileURLToPath(import.meta.url)), "..");
    const harness = await createHarnessSession({
      cwd,
      bridgeScript: resolve(cwd, "src/cs2_sim/agent_bridge.py"),
      skillDirs: [resolve(cwd, "skills")],
      allowedTools: ["analyze_replay"],
    }, new MemoryAuditSink());
    try {
      expect(harness.session.agent.state.tools.map((tool) => tool.name)).toEqual(["analyze_replay"]);
    } finally {
      harness.dispose();
    }
  });
});
