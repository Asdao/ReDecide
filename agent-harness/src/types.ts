/** Shared contracts owned by the harness, independent of Pi or the simulator. */

export type ToolEffect = "read" | "write" | "external";
export type ApprovalMode = "never" | "always" | "policy";

export interface ToolMetadata {
  readonly name: string;
  readonly label: string;
  readonly description: string;
  readonly effect: ToolEffect;
  readonly approval: ApprovalMode;
  readonly timeoutMs: number;
  readonly maxResultBytes: number;
  /** A conservative per-turn invocation limit for this tool. */
  readonly maxCallsPerTurn?: number;
}

export interface HarnessConfig {
  readonly cwd: string;
  readonly skillDirs: readonly string[];
  readonly allowedTools: readonly string[];
  readonly sessionMode: "memory" | "persisted";
  readonly maxToolCallsPerTurn: number;
  readonly toolTimeoutMs: number;
  readonly pythonExecutable: string;
  readonly bridgeScript: string;
  readonly bridgeCwd?: string;
  readonly maxBridgeOutputBytes: number;
  readonly model?: unknown;
  readonly modelRuntime?: unknown;
  readonly thinkingLevel?: string;
}

export interface BridgeRequest {
  readonly version: 1;
  readonly operation: string;
  readonly arguments: Record<string, unknown>;
}

export interface BridgeErrorEnvelope {
  readonly code: string;
  readonly message: string;
}

export interface BridgeSuccess<T = unknown> {
  readonly version: 1;
  readonly ok: true;
  readonly data: T;
}

export interface BridgeFailure {
  readonly version: 1;
  readonly ok: false;
  readonly error: BridgeErrorEnvelope;
}

export type BridgeResponse<T = unknown> = BridgeSuccess<T> | BridgeFailure;

export interface PolicyContext {
  readonly correlationId: string;
  readonly callId: string;
  readonly callsThisTurn: number;
  readonly approvedByUser?: boolean;
}

export interface PolicyDecision {
  readonly allowed: boolean;
  readonly reason: string;
  readonly metadata?: ToolMetadata;
}

export interface ToolExecutionContext {
  readonly correlationId: string;
  readonly callId: string;
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

export interface RegisteredTool<TArgs = unknown, TResult = unknown> {
  readonly metadata: ToolMetadata;
  readonly validate: (value: unknown) => TArgs;
  execute(args: TArgs, context: ToolExecutionContext): Promise<TResult>;
}

export type AuditEventType =
  | "request_started"
  | "request_finished"
  | "tool_requested"
  | "tool_allowed"
  | "tool_denied"
  | "tool_finished"
  | "tool_timeout"
  | "tool_cancelled"
  | "schema_error";

export interface AuditEvent {
  readonly timestamp: string;
  readonly type: AuditEventType;
  readonly correlationId: string;
  readonly callId?: string;
  readonly tool?: string;
  readonly allowed?: boolean;
  readonly status?: "ok" | "error" | "timeout" | "cancelled";
  readonly durationMs?: number;
  readonly inputBytes?: number;
  readonly outputBytes?: number;
  readonly reason?: string;
  readonly errorCode?: string;
}

export interface AuditSink {
  write(event: AuditEvent): void;
}
