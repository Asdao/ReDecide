import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PythonBridge, BridgeError } from "../src/bridge.js";

async function fixture(contents: string): Promise<{ dir: string; file: string }> {
  const dir = await mkdtemp(join(tmpdir(), "cs2-harness-"));
  const file = join(dir, "fixture.mjs");
  await writeFile(file, contents, "utf8");
  return { dir, file };
}

describe("JSON bridge", () => {
  it("validates versioned success envelopes without Python or credentials", async () => {
    const value = await fixture("process.stdin.resume(); process.stdin.on('end',()=>console.log(JSON.stringify({version:1,ok:true,data:{winner:'CT'}})));\n");
    try {
      const bridge = new PythonBridge({ executable: process.execPath, scriptPath: value.file, timeoutMs: 1000, maxOutputBytes: 4096, operations: ["simulate_round"] });
      await expect(bridge.call("simulate_round", { seed: 7 }, { correlationId: "c", callId: "x" })).resolves.toEqual({ winner: "CT" });
    } finally {
      await rm(value.dir, { recursive: true, force: true });
    }
  });

  it("fails closed on malformed JSON", async () => {
    const value = await fixture("console.log('not-json');\n");
    try {
      const bridge = new PythonBridge({ executable: process.execPath, scriptPath: value.file, timeoutMs: 1000, maxOutputBytes: 4096, operations: ["simulate_round"] });
      await expect(bridge.call("simulate_round", {}, { correlationId: "c", callId: "x" })).rejects.toMatchObject({ code: "INVALID_JSON" });
      await expect(bridge.call("unknown", {}, { correlationId: "c", callId: "x" })).rejects.toBeInstanceOf(BridgeError);
    } finally {
      await rm(value.dir, { recursive: true, force: true });
    }
  });

  it("returns a structured process error for an unavailable executable", async () => {
    const bridge = new PythonBridge({
      executable: "definitely-not-a-real-executable",
      scriptPath: "missing-script",
      timeoutMs: 1000,
      maxOutputBytes: 4096,
      operations: ["simulate_round"],
    });
    await expect(bridge.call("simulate_round", {}, { correlationId: "c", callId: "x" })).rejects.toMatchObject({ code: "BRIDGE_PROCESS" });
  });
});
