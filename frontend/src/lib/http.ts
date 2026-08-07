// Vercel Services routes same-origin /api requests to FastAPI through the
// root vercel.json rewrites. Local standalone-backend development can still
// provide an absolute API base URL.
export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";

export type ReplayUploadMode = "direct" | "blob";

function resolveReplayUploadMode(value: string | undefined): ReplayUploadMode {
  if (value === undefined || value === "" || value === "direct") {
    return "direct";
  }
  if (value === "blob") {
    return "blob";
  }
  throw new Error("NEXT_PUBLIC_REPLAY_UPLOAD_MODE must be either direct or blob");
}

export const replayUploadMode = resolveReplayUploadMode(
  process.env.NEXT_PUBLIC_REPLAY_UPLOAD_MODE,
);

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
