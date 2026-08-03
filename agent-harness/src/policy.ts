import type {
  AuditSink,
  PolicyContext,
  PolicyDecision,
  RegisteredTool,
  ToolMetadata,
} from "./types.js";
import { auditEvent } from "./audit.js";

export class ToolPolicyError extends Error {
  public constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "ToolPolicyError";
  }
}

/** Explicit registry and default-deny policy. Unknown names never reach a dispatcher. */
export class ToolRegistry {
  private readonly tools = new Map<string, RegisteredTool>();
  private readonly allowed: ReadonlySet<string>;

  public constructor(
    allowedTools: readonly string[],
    private readonly maxToolCallsPerTurn: number,
    private readonly audit: AuditSink,
  ) {
    if (!Number.isInteger(maxToolCallsPerTurn) || maxToolCallsPerTurn < 1) {
      throw new RangeError("maxToolCallsPerTurn must be a positive integer");
    }
    this.allowed = new Set(allowedTools);
  }

  public register<TArgs, TResult>(tool: RegisteredTool<TArgs, TResult>): void {
    const name = tool.metadata.name;
    if (!/^[a-z][a-z0-9_]{1,63}$/.test(name)) {
      throw new ToolPolicyError("INVALID_TOOL_NAME", `Invalid tool name: ${name}`);
    }
    if (this.tools.has(name)) {
      throw new ToolPolicyError("DUPLICATE_TOOL", `Tool already registered: ${name}`);
    }
    if (tool.metadata.timeoutMs <= 0 || tool.metadata.maxResultBytes <= 0) {
      throw new ToolPolicyError("INVALID_TOOL_LIMIT", `Invalid limits for ${name}`);
    }
    this.tools.set(name, tool as unknown as RegisteredTool);
  }

  public get(name: string): RegisteredTool | undefined {
    return this.tools.get(name);
  }

  public metadata(): readonly ToolMetadata[] {
    return [...this.tools.values()].map((tool) => tool.metadata);
  }

  public names(): readonly string[] {
    return [...this.tools.keys()];
  }

  public decide(name: string, context: PolicyContext): PolicyDecision {
    const metadata = this.tools.get(name)?.metadata;
    if (!metadata) {
      return { allowed: false, reason: "unknown_tool" };
    }
    if (!this.allowed.has(name)) {
      return { allowed: false, reason: "tool_not_allowlisted", metadata };
    }
    if (context.callsThisTurn >= this.maxToolCallsPerTurn) {
      return { allowed: false, reason: "turn_call_limit", metadata };
    }
    const perToolLimit = metadata.maxCallsPerTurn;
    if (perToolLimit !== undefined && context.callsThisTurn >= perToolLimit) {
      return { allowed: false, reason: "tool_call_limit", metadata };
    }
    if (metadata.approval === "always" && context.approvedByUser !== true) {
      return { allowed: false, reason: "approval_required", metadata };
    }
    // The POC registers read-only tools only; this check remains default-deny for future writes.
    if (metadata.effect !== "read" && context.approvedByUser !== true) {
      return { allowed: false, reason: "side_effect_approval_required", metadata };
    }
    return { allowed: true, reason: "allowed", metadata };
  }

  public assertAllowed(name: string, context: PolicyContext): RegisteredTool {
    const decision = this.decide(name, context);
    this.audit.write(
      auditEvent(decision.allowed ? "tool_allowed" : "tool_denied", context.correlationId, {
        callId: context.callId,
        tool: name,
        allowed: decision.allowed,
        reason: decision.reason,
      }),
    );
    if (!decision.allowed) {
      throw new ToolPolicyError("TOOL_DENIED", `${name}: ${decision.reason}`);
    }
    return this.tools.get(name)!;
  }
}
