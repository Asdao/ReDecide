import { uploadPresigned } from "@vercel/blob/client";
import { z } from "zod";
import {
  analysisJobSchema,
  analysisProgressEventSchema,
  analysisPlayersSchema,
  replayAnalysisResultSchema,
  replayManifestSchema,
  replayVisualizationSchema,
  type AnalysisJob,
  type AnalysisProgressEvent,
  type AnalysisPlayers,
  type ReplayAnalysisResult,
  type ReplayManifest,
  type ReplayVisualization,
} from "@/domain/replay";
import {
  apiBaseUrl,
  isAbortError,
  replayUploadMode,
  type ReplayUploadMode,
} from "@/lib/http";

const REPLAY_BLOB_UPLOAD_URL = "/api/blob/upload";
const REPLAY_BLOB_CLEANUP_URL = "/api/blob/cleanup";
const REPLAY_BLOB_MULTIPART_THRESHOLD_BYTES = 100 * 1024 * 1024;
const REPLAY_BLOB_MAX_BYTES = 1024 * 1024 * 1024;

type ReplayOperation =
  | "upload"
  | "prepare"
  | "analysis-status"
  | "players"
  | "coaching"
  | "intent-coaching"
  | "result"
  | "replay-status"
  | "visualization";

type AnalysisProgressHandlers = {
  onProgress: (progress: AnalysisProgressEvent) => void;
};

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

const intentCoachingResponseSchema = z
  .object({
    analysis_id: z.string().min(1),
    player_id: z.string().min(1),
    decision_id: z.string().min(1),
    user_intent: z.string().min(1),
    intent_feasibility: z.string().min(1),
    coordination_gap: z.string().min(1),
    recommended_cs2_adjustment: z.string().min(1),
    in_depth_coaching: z.string().min(1),
    knowledge_cutoff_tick: z.number().int().nonnegative(),
    facts_referenced: z.array(z.string().min(1)),
  })
  .strict();

export type IntentCoachingResponse = z.infer<typeof intentCoachingResponseSchema>;

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

export function subscribeToAnalysisProgress(
  eventsUrl: string,
  { onProgress }: AnalysisProgressHandlers,
): () => void {
  const normalizedPath = eventsUrl.startsWith("/") ? eventsUrl : `/${eventsUrl}`;
  const source = new EventSource(`${apiBaseUrl}${normalizedPath}`);
  let terminalEventReceived = false;

  const receive = (event: Event) => {
    if (!(event instanceof MessageEvent) || typeof event.data !== "string") {
      return;
    }
    let value: unknown;
    try {
      value = JSON.parse(event.data);
    } catch {
      return;
    }
    const parsed = analysisProgressEventSchema.safeParse(value);
    if (!parsed.success) {
      return;
    }
    onProgress(parsed.data);
    if (parsed.data.stage === "complete" || parsed.data.stage === "error") {
      terminalEventReceived = true;
    }
  };

  source.addEventListener("log", receive);
  source.addEventListener("complete", receive);
  source.onerror = () => {
    if (terminalEventReceived) {
      source.close();
    }
  };
  return () => source.close();
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
    return new ReplayApiError(
      operation === "upload"
        ? "Replay uploads are not enabled on the backend."
        : "This replay or analysis could not be found.",
      {
        kind: "not-found",
        operation,
        status,
      },
    );
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
  if (status === 413 && operation === "upload") {
    return new ReplayApiError("Choose a smaller .dem replay file.", {
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

async function uploadReplayDirect(file: File, signal?: AbortSignal): Promise<ReplayManifest> {
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

async function deleteTemporaryReplayBlob(blobUrl: string): Promise<void> {
  try {
    await fetch(REPLAY_BLOB_CLEANUP_URL, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url: blobUrl }),
      keepalive: true,
    });
  } catch {
    // Cleanup is best-effort: a prepared replay must remain usable if Blob
    // deletion is temporarily unavailable.
  }
}

async function uploadReplayViaBlob(file: File, signal?: AbortSignal): Promise<ReplayManifest> {
  if (file.size > REPLAY_BLOB_MAX_BYTES) {
    throw new ReplayApiError("Choose a .dem file smaller than 1 GB.", {
      kind: "invalid-file",
      operation: "upload",
    });
  }

  let blobUrl: string;
  try {
    const blob = await uploadPresigned(`uploads/${file.name}`, file, {
      access: "public",
      handleUploadUrl: REPLAY_BLOB_UPLOAD_URL,
      contentType: "application/octet-stream",
      multipart: file.size > REPLAY_BLOB_MULTIPART_THRESHOLD_BYTES,
      abortSignal: signal,
    });
    blobUrl = blob.url;
  } catch (error: unknown) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ReplayApiError("The replay could not be uploaded to temporary storage.", {
      kind: "network",
      operation: "upload",
    });
  }

  const response = await request(
    "/api/replay/import-url",
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url: blobUrl, filename: file.name }),
      signal,
    },
    "upload",
  );
  const manifest = await parseSuccessful(response, replayManifestSchema, "upload");
  if (manifest.visualization_status === "ready") {
    await deleteTemporaryReplayBlob(blobUrl);
  }
  return manifest;
}

export async function uploadReplay(
  file: File,
  signal?: AbortSignal,
  mode: ReplayUploadMode = replayUploadMode,
): Promise<ReplayManifest> {
  if (!file.name.toLowerCase().endsWith(".dem")) {
    throw new ReplayApiError("Choose a valid .dem replay file.", {
      kind: "invalid-file",
      operation: "upload",
    });
  }

  return mode === "blob"
    ? uploadReplayViaBlob(file, signal)
    : uploadReplayDirect(file, signal);
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

export async function submitPlayerIntent(
  analysisId: string,
  playerId: string,
  decisionId: string,
  intentText: string,
  signal?: AbortSignal,
): Promise<IntentCoachingResponse> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}/intent`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        analysis_id: analysisId,
        player_id: playerId,
        decision_id: decisionId,
        intent_text: intentText,
      }),
      signal,
    },
    "intent-coaching",
  );
  const result = await parseSuccessful(
    response,
    intentCoachingResponseSchema,
    "intent-coaching",
  );
  if (
    result.analysis_id !== analysisId ||
    result.player_id !== playerId ||
    result.decision_id !== decisionId
  ) {
    throw new ReplayApiError("The backend returned data for a different replay moment.", {
      kind: "invalid-response",
      operation: "intent-coaching",
      status: response.status,
    });
  }
  return result;
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

const intentCoachingResponseSchema = z
  .object({
    analysis_id: z.string(),
    player_id: z.string(),
    decision_id: z.string(),
    user_intent: z.string(),
    intent_feasibility: z.string(),
    coordination_gap: z.string(),
    recommended_cs2_adjustment: z.string(),
    in_depth_coaching: z.string(),
    knowledge_cutoff_tick: z.number(),
    facts_referenced: z.array(z.string()),
  })
  .strict();

export type IntentCoachingResponse = z.infer<typeof intentCoachingResponseSchema>;

export async function submitPlayerIntent(
  analysisId: string,
  playerId: string,
  decisionId: string,
  intentText: string,
  signal?: AbortSignal,
): Promise<IntentCoachingResponse> {
  const response = await request(
    `/api/analysis/${resourcePath(analysisId)}/intent`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        analysis_id: analysisId,
        player_id: playerId,
        decision_id: decisionId,
        intent_text: intentText,
      }),
      signal,
    },
    "coaching",
  );
  return parseSuccessful(response, intentCoachingResponseSchema, "coaching");
}
