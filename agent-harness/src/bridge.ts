import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import type { AuditSink, ToolExecutionContext } from "./types.js";
import type { BridgeRequest, BridgeResponse } from "./types.js";
import { auditEvent } from "./audit.js";

export class BridgeError extends Error {
  public constructor(
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "BridgeError";
  }
}

export interface PythonBridgeOptions {
  readonly executable: string;
  readonly scriptPath: string;
  readonly cwd?: string;
  readonly timeoutMs: number;
  readonly maxOutputBytes: number;
  readonly operations?: readonly string[];
  readonly audit?: AuditSink;
}

const DEFAULT_OPERATIONS = ["simulate_round", "analyze_replay"] as const;

/** Process-per-call JSON bridge. Never invokes a shell and kills children on timeout/abort. */
export class PythonBridge {
  private readonly operations: ReadonlySet<string>;

  public constructor(private readonly options: PythonBridgeOptions) {
    if (!Number.isInteger(options.timeoutMs) || options.timeoutMs <= 0) {
      throw new RangeError("bridge timeoutMs must be a positive integer");
    }
    if (!Number.isInteger(options.maxOutputBytes) || options.maxOutputBytes < 256) {
      throw new RangeError("bridge maxOutputBytes must be at least 256 bytes");
    }
    this.operations = new Set(options.operations ?? DEFAULT_OPERATIONS);
  }

  public async call<T>(
    operation: string,
    args: Record<string, unknown>,
    context: ToolExecutionContext,
  ): Promise<T> {
    if (!this.operations.has(operation)) {
      throw new BridgeError("UNKNOWN_OPERATION", `Unsupported bridge operation: ${operation}`);
    }
    const request: BridgeRequest = { version: 1, operation, arguments: args };
    const started = performance.now();
    const timeoutMs = context.timeoutMs ?? this.options.timeoutMs;
    context.signal?.throwIfAborted();
    let child: ChildProcess;
    try {
      child = spawn(this.options.executable, [this.options.scriptPath], {
        cwd: this.options.cwd,
        shell: false,
        windowsHide: true,
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to start bridge process";
      throw new BridgeError("BRIDGE_PROCESS", message);
    }
    let timer: NodeJS.Timeout | undefined;
    let timedOut = false;
    let cancelled = false;
    let settled = false;
    let processError: Error | undefined;
    child.once("error", (error: Error) => {
      processError = error;
    });
    const abort = (): void => {
      if (settled) return;
      cancelled = true;
      terminateChild(child);
    };
    context.signal?.addEventListener("abort", abort, { once: true });
    timer = setTimeout(() => {
      if (settled) return;
      timedOut = true;
      terminateChild(child);
    }, timeoutMs);

    let stdoutBytes = 0;
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    child.stdout?.on("data", (chunk: Buffer | string) => {
      const bytes = Buffer.byteLength(chunk);
      stdoutBytes += bytes;
      if (stdoutBytes > this.options.maxOutputBytes) {
        terminateChild(child);
        return;
      }
      stdout.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    });
    child.stderr?.on("data", (chunk: Buffer | string) => {
      // Stderr is diagnostic only and is bounded to avoid retaining arbitrary logs.
      if (Buffer.concat(stderr).byteLength < 32_768) {
        stderr.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
    });

    try {
      child.stdin?.end(`${JSON.stringify(request)}\n`);
      const [exitCode, signal] = await once(child, "close") as [number | null, NodeJS.Signals | null];
      settled = true;
      if (processError) {
        throw new BridgeError("BRIDGE_PROCESS", processError.message);
      }
      if (timedOut) {
        this.options.audit?.write(auditEvent("tool_timeout", context.correlationId, {
          callId: context.callId,
          tool: operation,
          durationMs: Math.round(performance.now() - started),
          status: "timeout",
        }));
        throw new BridgeError("BRIDGE_TIMEOUT", `Bridge operation timed out after ${timeoutMs}ms`);
      }
      if (cancelled || context.signal?.aborted) {
        this.options.audit?.write(auditEvent("tool_cancelled", context.correlationId, {
          callId: context.callId,
          tool: operation,
          durationMs: Math.round(performance.now() - started),
          status: "cancelled",
        }));
        throw new BridgeError("BRIDGE_CANCELLED", "Bridge operation cancelled");
      }
      if (stdoutBytes > this.options.maxOutputBytes) {
        throw new BridgeError("OUTPUT_TOO_LARGE", "Bridge output exceeded configured limit");
      }
      const result = this.parseResponse(Buffer.concat(stdout).toString("utf8"), operation);
      if (exitCode !== 0 && result.ok) {
        throw new BridgeError("BRIDGE_EXIT", `Bridge exited with code ${String(exitCode)}`);
      }
      if (!result.ok) {
        throw new BridgeError(result.error.code, result.error.message);
      }
      this.options.audit?.write(auditEvent("tool_finished", context.correlationId, {
        callId: context.callId,
        tool: operation,
        durationMs: Math.round(performance.now() - started),
        outputBytes: Buffer.byteLength(JSON.stringify(result.data)),
        status: "ok",
      }));
      return result.data as T;
    } catch (error) {
      settled = true;
      if (error instanceof BridgeError) throw error;
      const message = error instanceof Error ? error.message : "Bridge process failed";
      throw new BridgeError("BRIDGE_PROCESS", message);
    } finally {
      if (timer) clearTimeout(timer);
      context.signal?.removeEventListener("abort", abort);
      // Keep the process boundary strict even if an implementation emits close late.
      if (!settled) terminateChild(child);
    }
  }

  private parseResponse(raw: string, operation: string): BridgeResponse {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new BridgeError("INVALID_JSON", `Bridge returned invalid JSON for ${operation}`);
    }
    if (!isRecord(parsed) || parsed.version !== 1 || typeof parsed.ok !== "boolean") {
      throw new BridgeError("INVALID_ENVELOPE", "Bridge response has an invalid version or ok flag");
    }
    if (parsed.ok === true) {
      if (!("data" in parsed)) throw new BridgeError("INVALID_ENVELOPE", "Successful bridge response is missing data");
      return parsed as unknown as BridgeResponse;
    }
    if (!isRecord(parsed.error) || typeof parsed.error.code !== "string" || typeof parsed.error.message !== "string") {
      throw new BridgeError("INVALID_ENVELOPE", "Failed bridge response is missing a stable error");
    }
    return parsed as unknown as BridgeResponse;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function terminateChild(child: ChildProcess): void {
  if (child.exitCode !== null || child.signalCode !== null || child.killed) return;
  child.kill("SIGTERM");
  const force = setTimeout(() => {
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
  }, 250);
  force.unref();
}
