import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { AuditEvent, AuditSink } from "./types.js";

/** Writes one bounded JSON object per line. Payloads are intentionally absent. */
export class JsonlAuditSink implements AuditSink {
  public constructor(private readonly path: string) {
    mkdirSync(dirname(path), { recursive: true });
  }

  public write(event: AuditEvent): void {
    appendFileSync(this.path, `${JSON.stringify(event)}\n`, "utf8");
  }
}

/** Useful for tests and callers that want to forward events to their own logger. */
export class MemoryAuditSink implements AuditSink {
  public readonly events: AuditEvent[] = [];

  public write(event: AuditEvent): void {
    this.events.push(Object.freeze({ ...event }));
  }
}

export function noopAuditSink(): AuditSink {
  return { write: () => undefined };
}

export function auditEvent(
  type: AuditEvent["type"],
  correlationId: string,
  details: Omit<AuditEvent, "timestamp" | "type" | "correlationId"> = {},
): AuditEvent {
  return {
    timestamp: new Date().toISOString(),
    type,
    correlationId,
    ...details,
  };
}
