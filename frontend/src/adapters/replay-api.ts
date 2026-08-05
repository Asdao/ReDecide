import { z } from "zod";
import {
  analysisJobSchema,
  analysisPlayersSchema,
  replayAnalysisResultSchema,
  replayManifestSchema,
  replayVisualizationSchema,
  type AnalysisJob,
  type AnalysisPlayers,
  type ReplayAnalysisResult,
  type ReplayManifest,
  type ReplayVisualization,
} from "@/domain/replay";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

type ReplayOperation =
  | "upload"
  | "prepare"
  | "analysis-status"
  | "players"
  | "coaching"
  | "result"
  | "replay-status"
  | "visualization";

export type ReplayApiErrorKind =
  | "invalid-file"
  | "network"
  | "non-json"
  | "malformed-json"
  | "invalid-response"
  | "not-found"
  | "not-ready"
  | "rejected"
  | "server";

export class ReplayApiError extends Error {
  readonly kind: ReplayApiErrorKind;
  readonly operation: ReplayOperation;
  readonly status?: number;

  constructor(
    message: string,
    options: {
      kind: ReplayApiErrorKind;
      operation: ReplayOperation;
      status?: number;
    },
  ) {
    super(message);
    this.name = "ReplayApiError";
    this.kind = options.kind;
    this.operation = options.operation;
    this.status = options.status;
  }
}

type PendingOrReady<T> = { state: "processing" } | { state: "ready"; value: T };

export type VisualizationResponse =
  | { state: "processing" }
  | { state: "locked" }
  | { state: "failed" }
  | { state: "ready"; value: ReplayVisualization };

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

async function request(
  url: string,
  init: RequestInit,
  operation: ReplayOperation,
): Promise<Response> {
  try {
    return await fetch(`${apiBaseUrl}${url}`, init);
  } catch (error: unknown) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ReplayApiError("The backend could not be reached.", {
      kind: "network",
      operation,
    });
  }
}

async function readJson(response: Response, operation: ReplayOperation): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new ReplayApiError("The backend returned an unexpected response.", {
      kind: "non-json",
      operation,
      status: response.status,
    });
  }

  try {
    return await response.json();
  } catch {
    throw new ReplayApiError("The backend returned unreadable data.", {
      kind: "malformed-json",
      operation,
      status: response.status,
    });
  }
}

function safeHttpError(operation: ReplayOperation, status: number): ReplayApiError {
  if (status === 404) {
    return new ReplayApiError("This replay or analysis could not be found.", {
      kind: "not-found",
      operation,
      status,
    });
  }
  if (status === 409) {
    return new ReplayApiError("This analysis is not ready for that action yet.", {
      kind: "not-ready",
      operation,
      status,
    });
  }
  if (status === 415) {
    return new ReplayApiError("Choose a valid .dem replay file.", {
      kind: "invalid-file",
      operation,
      status,
    });
  }
  if (status === 422) {
    return new ReplayApiError(
      operation === "upload"
        ? "The selected replay could not be parsed."
        : "The backend rejected this replay request.",
      { kind: "rejected", operation, status },
    );
  }
  return new ReplayApiError("The backend could not complete this request.", {
    kind: status >= 500 ? "server" : "rejected",
    operation,
    status,
  });
}

async function parseSuccessful<T>(
  response: Response,
  schema: z.ZodType<T>,
  operation: ReplayOperation,
): Promise<T> {
  const payload = await readJson(response, operation);
  if (!response.ok) {
    throw safeHttpError(operation, response.status);
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ReplayApiError("The backend returned data in an unexpected format.", {
      kind: "invalid-response",
      operation,
      status: response.status,
    });
  }
  return parsed.data;
}

function resourcePath(segment: string): string {
  return encodeURIComponent(segment);
}

export async function uploadReplay(file: File, signal?: AbortSignal): Promise<ReplayManifest> {
  if (!file.name.toLowerCase().endsWith(".dem")) {
    throw new ReplayApiError("Choose a valid .dem replay file.", {
      kind: "invalid-file",
      operation: "upload",
    });
  }

  const body = new FormData();
  body.set("file", file);
  const response = await request(
    "/api/replay/upload",
    {
      method: "POST",
      headers: { Accept: "application/json" },
      body,
      signal,
    },
    "upload",
  );
  return parseSuccessful(response, replayManifestSchema, "upload");
}

export async function prepareReplayAnalysis(
  replayId: string,
  signal?: AbortSignal,
): Promise<AnalysisJob> {
  const response = await request(
    "/api/analysis/prepare",
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ replay_id: replayId }),
      signal,
    },
    "prepare",
  );
  return parseSuccessful(response, analysisJobSchema, "prepare");
}

export function prepareReplayWorkspace(
  replayId: string,
  signal?: AbortSignal,
): Promise<AnalysisJob> {
  const preparation = prepareReplayAnalysis(replayId, signal);
  void getReplayVisualization(replayId, signal).catch(() => undefined);
  return preparation;
}

export async function getAnalysisStatus(
  analysisId: string,
  signal?: AbortSignal,
): Promise<AnalysisJob> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}`,
    { method: "GET", headers: { Accept: "application/json" }, signal },
    "analysis-status",
  );
  return parseSuccessful(response, analysisJobSchema, "analysis-status");
}

export async function getAnalysisPlayers(
  analysisId: string,
  signal?: AbortSignal,
): Promise<PendingOrReady<AnalysisPlayers>> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}/players`,
    { method: "GET", headers: { Accept: "application/json" }, signal },
    "players",
  );
  if (response.status === 202) {
    return { state: "processing" };
  }
  return {
    state: "ready",
    value: await parseSuccessful(response, analysisPlayersSchema, "players"),
  };
}

export async function runReplayCoaching(
  analysisId: string,
  playerId: string,
  signal?: AbortSignal,
): Promise<ReplayAnalysisResult> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}/run`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ player_id: playerId }),
      signal,
    },
    "coaching",
  );
  return parseSuccessful(response, replayAnalysisResultSchema, "coaching");
}

export async function getAnalysisResult(
  analysisId: string,
  signal?: AbortSignal,
): Promise<PendingOrReady<ReplayAnalysisResult>> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}/result`,
    { method: "GET", headers: { Accept: "application/json" }, signal },
    "result",
  );
  if (response.status === 202) {
    return { state: "processing" };
  }
  return {
    state: "ready",
    value: await parseSuccessful(response, replayAnalysisResultSchema, "result"),
  };
}

export async function getReplayStatus(
  replayId: string,
  signal?: AbortSignal,
): Promise<ReplayManifest> {
  const response = await request(
    `/api/replay/${resourcePath(replayId)}/status`,
    { method: "GET", headers: { Accept: "application/json" }, signal },
    "replay-status",
  );
  return parseSuccessful(response, replayManifestSchema, "replay-status");
}

export async function getReplayVisualization(
  replayId: string,
  signal?: AbortSignal,
): Promise<VisualizationResponse> {
  const response = await request(
    `/api/replay/${resourcePath(replayId)}/json`,
    { method: "GET", headers: { Accept: "application/json" }, signal },
    "visualization",
  );
  if (response.status === 202) {
    return { state: "processing" };
  }
  if (response.status === 403) {
    return { state: "locked" };
  }
  if (response.status === 422) {
    return { state: "failed" };
  }
  return {
    state: "ready",
    value: await parseSuccessful(response, replayVisualizationSchema, "visualization"),
  };
}
