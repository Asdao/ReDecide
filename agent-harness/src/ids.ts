import { randomUUID } from "node:crypto";

export function newCorrelationId(): string {
  return randomUUID();
}

export function newCallId(): string {
  return randomUUID();
}
