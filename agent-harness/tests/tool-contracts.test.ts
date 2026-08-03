import { describe, expect, it } from "vitest";
import { validateComparePolicies } from "../src/tools/compare-policies.js";
import { boundedJson } from "../src/tools/common.js";
import { validateInspectLegalActions } from "../src/tools/inspect-legal-actions.js";
import { validateSimulateRound } from "../src/tools/simulate-round.js";

describe("domain tool contracts", () => {
  it("accepts documented simulation arguments and rejects unknown fields", () => {
    expect(validateSimulateRound({ seed: 7, scenario: "example", policy: "baseline" })).toEqual({ seed: 7, scenario: "example", policy: "baseline" });
    expect(() => validateSimulateRound({ scenario: "example", policy: "baseline", extra: true })).toThrow(/Unknown argument/);
    expect(() => validateSimulateRound({ seed: 2 ** 40, scenario: "example", policy: "baseline" })).toThrow(/signed 32-bit/);
    expect(() => validateSimulateRound({ scenario: "missing", policy: "baseline" })).toThrow(/Unknown scenario/);
  });

  it("bounds state, policy, and seed inputs", () => {
    expect(validateInspectLegalActions({ state: { round: 1 }, player: "T" }).player).toBe("T");
    expect(validateComparePolicies({ scenario: "example", policies: ["baseline"], seeds: [1, 2] }).seeds).toEqual([1, 2]);
    expect(() => validateComparePolicies({ scenario: "x", policies: [] })).toThrow(/1-4/);
  });

  it("returns deterministic bounded output text", () => {
    const output = boundedJson({ events: ["x".repeat(100)] }, 30);
    expect(Buffer.byteLength(output)).toBeGreaterThan(0);
    expect(Buffer.byteLength(output)).toBeLessThanOrEqual(40);
    expect(output).toContain("truncated");
  });
});
