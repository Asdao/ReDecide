import { issueSignedToken, presignUrl } from "@vercel/blob";

const ARTIFACT_CONTENT_TYPE = "application/json";
const MAX_ARTIFACT_BYTES = 128 * 1024 * 1024;
const SIGNED_URL_TTL_MS = 5 * 60 * 1000;
const REPLAY_ID = "[0-9a-f]{32}";
const ANALYSIS_ID = "[A-Za-z0-9._%~-]{1,200}";

type BlobAccess = "public" | "private";
type BlobOperation = "get" | "head" | "put";

interface TicketRequest {
  operation: BlobOperation;
  pathname: string;
  access: BlobAccess;
  contentType?: string;
  size?: number;
}

export const runtime = "nodejs";

function configuredAccess(): BlobAccess {
  return process.env.REDECIDE_BLOB_ACCESS === "private" ? "private" : "public";
}

function escapedPrefix(name: string, fallback: string): string {
  const prefix = (process.env[name] ?? fallback).replace(/^\/+|\/+$/g, "");
  return prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function allowedPathname(pathname: string): boolean {
  if (
    pathname.length > 512 ||
    pathname.includes("\\") ||
    pathname.includes("..") ||
    pathname.includes("?") ||
    pathname.includes("#")
  ) {
    return false;
  }

  const replayPrefix = escapedPrefix("REDECIDE_BLOB_REPLAY_PREFIX", "replays");
  const analysisPrefix = escapedPrefix("REDECIDE_BLOB_ANALYSIS_PREFIX", "analysis");
  const replayArtifact = new RegExp(
    `^${replayPrefix}/${REPLAY_ID}/(?:manifest|coaching|visualization)\\.json$`,
  );
  const analysisArtifact = new RegExp(
    `^${analysisPrefix}/${ANALYSIS_ID}/(?:state|result)\\.json$`,
  );
  return replayArtifact.test(pathname) || analysisArtifact.test(pathname);
}

function parseTicket(value: unknown): TicketRequest | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const body = value as Record<string, unknown>;
  if (
    !["get", "head", "put"].includes(String(body.operation)) ||
    typeof body.pathname !== "string" ||
    !allowedPathname(body.pathname) ||
    (body.access !== "public" && body.access !== "private") ||
    body.access !== configuredAccess()
  ) {
    return null;
  }

  const operation = body.operation as BlobOperation;
  if (operation === "put") {
    if (
      body.contentType !== ARTIFACT_CONTENT_TYPE ||
      !Number.isSafeInteger(body.size) ||
      (body.size as number) <= 0 ||
      (body.size as number) > MAX_ARTIFACT_BYTES
    ) {
      return null;
    }
  } else if (body.contentType !== undefined || body.size !== undefined) {
    return null;
  }

  return {
    operation,
    pathname: body.pathname,
    access: body.access,
    ...(operation === "put"
      ? { contentType: ARTIFACT_CONTENT_TYPE, size: body.size as number }
      : {}),
  };
}

function errorResponse(message: string, status: number): Response {
  return Response.json({ error: message }, { status });
}

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse("The Blob artifact request was invalid.", 400);
  }

  const ticket = parseTicket(body);
  if (ticket === null) {
    return errorResponse("The Blob artifact request was invalid.", 400);
  }

  const validUntil = Date.now() + SIGNED_URL_TTL_MS;
  try {
    const signedToken = await issueSignedToken({
      pathname: ticket.pathname,
      operations: [ticket.operation],
      validUntil,
      ...(ticket.operation === "put"
        ? {
            allowedContentTypes: [ARTIFACT_CONTENT_TYPE],
            maximumSizeInBytes: ticket.size,
          }
        : {}),
    });

    const common = {
      pathname: ticket.pathname,
      access: ticket.access,
      validUntil,
    } as const;
    const { presignedUrl } =
      ticket.operation === "put"
        ? await presignUrl(signedToken, {
            ...common,
            operation: "put",
            allowedContentTypes: [ARTIFACT_CONTENT_TYPE],
            maximumSizeInBytes: ticket.size,
            allowOverwrite: true,
            addRandomSuffix: false,
            cacheControlMaxAge: 60,
          })
        : ticket.operation === "head"
          ? await presignUrl(signedToken, { ...common, operation: "head" })
          : await presignUrl(signedToken, {
              ...common,
              operation: "get",
              ...(ticket.access === "private" ? { useCache: false } : {}),
            });

    return Response.json({ url: presignedUrl, expiresAt: validUntil });
  } catch (error: unknown) {
    console.error("[service-internal/blob-artifacts] signing failed", {
      name: error instanceof Error ? error.name : "UnknownError",
      message: error instanceof Error ? error.message : "Unknown Blob signing error",
    });
    return errorResponse("The Blob artifact request could not be authorized.", 502);
  }
}
