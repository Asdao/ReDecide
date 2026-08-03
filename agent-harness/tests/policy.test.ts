import { describe, expect, it } from "vitest";
import { MemoryAuditSink } from "../src/audit.js";
import { ToolRegistry } from "../src/policy.js";
import { executeThroughPolicy } from "../src/tools/common.js";
import { ToolInputError } from "../src/tools/common.js";

const metadata = {
  name: "fixture_tool",
  label: "Fixture",
  description: "A test-only read tool",
  effect: "read" as const,
  approval: "never" as const,
  timeoutMs: 1000,
  maxResultBytes: 1000,
};

describe("ToolRegistry", () => {
  it("denies unknown and non-allowlisted tools", () => {
    const audit = new MemoryAuditSink();
    const registry = new ToolRegistry(["fixture_tool"], 2, audit);
    registry.register({ metadata, validate: (value) => value, execute: async () => ({ ok: true }) });
    expect(registry.decide("missing", { correlationId: "c", callId: "x", callsThisTurn: 0 }).allowed).toBe(false);
    expect(registry.decide("fixture_tool", { correlationId: "c", callId: "x", callsThisTurn: 0 }).allowed).toBe(true);
    expect(registry.decide("fixture_tool", { correlationId: "c", callId: "x", callsThisTurn: 2 }).reason).toBe("turn_call_limit");
  });

  it("returns structured schema errors", async () => {
    const audit = new MemoryAuditSink();
    const registry = new ToolRegistry(["fixture_tool"], 2, audit);
    registry.register({
      metadata,
      validate: () => { throw new ToolInputError("BAD_INPUT", "bad input"); },
      execute: async () => "unreachable",
    });
    const result = await executeThroughPolicy(registry, audit, "fixture_tool", {}, { correlationId: "c", callId: "x", callsThisTurn: 0 });
    expect(result).toEqual({ ok: false, error: { code: "BAD_INPUT", message: "bad input" } });
    expect(audit.events.some((event) => event.type === "schema_error")).toBe(true);
  });
});
