// Vercel Services exposes the backend under the generated
// NEXT_PUBLIC_BACKEND_URL variable (normally ``/backend``). Keep the older
// API_BASE_URL fallback for existing local .env files and standalone backend
// development, but use the same-origin Services path by default.
export const apiBaseUrl =
  (
    process.env.NEXT_PUBLIC_BACKEND_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "/backend"
  ).replace(/\/$/, "");

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
