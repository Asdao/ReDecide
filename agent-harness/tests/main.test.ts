import { describe, expect, it } from "vitest";
import { resolve } from "node:path";
import { parseArgs } from "../src/main.js";

describe("harness CLI argument parsing", () => {
  const packageRoot = resolve("agent-harness");

  it("enables replay analysis when a replay is supplied", () => {
    const parsed = parseArgs(["--replay", "match.dem"], packageRoot);
    expect(parsed.replay).toBe("match.dem");
    expect(parsed.tools).toEqual(["simulate_round", "analyze_replay"]);
  });

  it("supports a server-side Pi invocation with no tools", () => {
    expect(parseArgs(["--replay", "match.dem", "--no-tools"], packageRoot).tools).toEqual([]);
    // The explicit no-tools choice remains authoritative even when it appears first.
    expect(parseArgs(["--no-tools", "--replay", "match.dem"], packageRoot).tools).toEqual([]);
  });

  it("rejects unknown options instead of silently forwarding them to Pi", () => {
    expect(() => parseArgs(["--unknown"], packageRoot)).toThrow("Unknown option: --unknown");
  });
});
