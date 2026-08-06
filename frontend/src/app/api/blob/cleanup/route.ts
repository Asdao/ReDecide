import { del } from "@vercel/blob";

const PUBLIC_BLOB_HOST_SUFFIX = ".public.blob.vercel-storage.com";
const TEMPORARY_REPLAY_PREFIX = "/uploads/";

export const runtime = "nodejs";

function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (origin === null) {
    return false;
  }

  try {
    return new URL(origin).origin === new URL(request.url).origin;
  } catch {
    return false;
  }
}

function temporaryReplayUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2048) {
    return null;
  }

  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
    if (
      url.protocol !== "https:" ||
      !hostname.endsWith(PUBLIC_BLOB_HOST_SUFFIX) ||
      hostname.length <= PUBLIC_BLOB_HOST_SUFFIX.length ||
      url.port !== "" ||
      url.username !== "" ||
      url.password !== "" ||
      url.search !== "" ||
      url.hash !== "" ||
      !url.pathname.startsWith(TEMPORARY_REPLAY_PREFIX) ||
      !url.pathname.toLowerCase().endsWith(".dem")
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function errorResponse(message: string, status: number): Response {
  return Response.json({ error: message }, { status });
}

export async function POST(request: Request): Promise<Response> {
  if (process.env.NEXT_PUBLIC_REPLAY_UPLOAD_MODE !== "blob") {
    return errorResponse("Blob replay uploads are not enabled.", 404);
  }
  if (!isSameOrigin(request)) {
    return errorResponse("The cleanup request was not allowed.", 403);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse("The cleanup request was invalid.", 400);
  }
  const blobUrl =
    body !== null && typeof body === "object" && "url" in body
      ? temporaryReplayUrl(body.url)
      : null;
  if (blobUrl === null) {
    return errorResponse("The cleanup request was invalid.", 400);
  }

  try {
    await del(blobUrl);
    return new Response(null, { status: 204 });
  } catch (error: unknown) {
    console.error("[api/blob/cleanup] deletion failed", {
      name: error instanceof Error ? error.name : "UnknownError",
    });
    return errorResponse("The temporary replay could not be deleted.", 502);
  }
}
