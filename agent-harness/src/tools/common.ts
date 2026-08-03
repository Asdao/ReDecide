import type { AuditSink, RegisteredTool, ToolExecutionContext } from "../types.js";
import { auditEvent } from "../audit.js";
import { ToolPolicyError, ToolRegistry } from "../policy.js";

export class ToolInputError extends Error {
  public constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "ToolInputError";
  }
}

export interface ToolResult {
  readonly ok: boolean;
  readonly data?: unknown;
  readonly error?: { readonly code: string; readonly message: string };
}

export function executeThroughPolicy(
  registry: ToolRegistry,
  audit: AuditSink,
  name: string,
  rawArgs: unknown,
  context: ToolExecutionContext & { readonly callsThisTurn: number; readonly approvedByUser?: boolean },
): Promise<ToolResult> {
  const started = performance.now();
  const callId = context.callId;
  audit.write(auditEvent("tool_requested", context.correlationId, {
    callId,
    tool: name,
    inputBytes: byteLength(rawArgs),
  }));
  let tool: RegisteredTool;
  try {
    tool = registry.assertAllowed(name, context);
  } catch (error) {
    const policyError = error instanceof ToolPolicyError ? error : new ToolPolicyError("TOOL_DENIED", "Tool denied");
    return Promise.resolve({ ok: false, error: { code: policyError.code, message: policyError.message } });
  }
  let args: unknown;
  try {
    args = tool.validate(rawArgs);
  } catch (error) {
    const inputError = error instanceof ToolInputError ? error : new ToolInputError("INVALID_ARGUMENTS", "Invalid tool arguments");
    audit.write(auditEvent("schema_error", context.correlationId, {
      callId,
      tool: name,
      durationMs: Math.round(performance.now() - started),
      status: "error",
      errorCode: inputError.code,
    }));
    return Promise.resolve({ ok: false, error: { code: inputError.code, message: inputError.message } });
  }
  return tool.execute(args, context).then(
    (data) => {
      audit.write(auditEvent("tool_finished", context.correlationId, {
        callId,
        tool: name,
        durationMs: Math.round(performance.now() - started),
        outputBytes: byteLength(data),
        status: "ok",
      }));
      return { ok: true, data };
    },
    (error: unknown) => {
      const code = isCodeError(error) ? error.code : "TOOL_EXECUTION_ERROR";
      const message = error instanceof Error ? error.message : "Tool execution failed";
      const status = code === "BRIDGE_TIMEOUT" ? "timeout" : code === "BRIDGE_CANCELLED" ? "cancelled" : "error";
      audit.write(auditEvent(status === "timeout" ? "tool_timeout" : status === "cancelled" ? "tool_cancelled" : "tool_finished", context.correlationId, {
        callId,
        tool: name,
        durationMs: Math.round(performance.now() - started),
        status,
        errorCode: code,
      }));
      return { ok: false, error: { code, message: sanitizeError(message) } };
    },
  );
}

export function byteLength(value: unknown): number {
  try {
    return Buffer.byteLength(JSON.stringify(value));
  } catch {
    return 0;
  }
}

/** Serialize a result while keeping the text passed back to the model bounded. */
export function boundedJson(value: unknown, maxBytes: number): string {
  if (!Number.isInteger(maxBytes) || maxBytes < 1) throw new RangeError("maxBytes must be positive");
  const raw = JSON.stringify(value);
  if (Buffer.byteLength(raw, "utf8") <= maxBytes) return raw;
  const suffix = `...${JSON.stringify({ truncated: true, originalBytes: Buffer.byteLength(raw, "utf8") })}`;
  const suffixBytes = Buffer.byteLength(suffix, "utf8");
  if (suffixBytes >= maxBytes) return suffix.slice(0, maxBytes);
  const prefixBytes = maxBytes - suffixBytes;
  return `${Buffer.from(raw, "utf8").subarray(0, prefixBytes).toString("utf8")}${suffix}`;
}

function sanitizeError(message: string): string {
  return message.replace(/([A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z_]*\s*[=:]\s*)[^\s,;]+/gi, "$1[redacted]").slice(0, 500);
}

function isCodeError(value: unknown): value is { code: string } {
  return typeof value === "object" && value !== null && "code" in value && typeof (value as { code?: unknown }).code === "string";
}

