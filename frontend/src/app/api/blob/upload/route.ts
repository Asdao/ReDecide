import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

const REPLAY_BLOB_MAX_BYTES = 1024 * 1024 * 1024;
const TOKEN_REQUEST_TYPE = "blob.generate-client-token";

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

function isDemoPathname(pathname: string): boolean {
  return pathname.toLowerCase().endsWith(".dem");
}

function errorResponse(message: string, status: number): Response {
  return Response.json({ error: message }, { status });
}

export async function POST(request: Request): Promise<Response> {
  if (process.env.NEXT_PUBLIC_REPLAY_UPLOAD_MODE !== "blob") {
    return errorResponse("Blob replay uploads are not enabled.", 404);
  }

  let rawBody: unknown;
  try {
    rawBody = await request.json();
  } catch {
    return errorResponse("The upload request was invalid.", 400);
  }
  if (
    rawBody === null ||
    typeof rawBody !== "object" ||
    !("type" in rawBody) ||
    typeof rawBody.type !== "string"
  ) {
    return errorResponse("The upload request was invalid.", 400);
  }
  const body = rawBody as HandleUploadBody;

  if (body.type === TOKEN_REQUEST_TYPE && !isSameOrigin(request)) {
    return errorResponse("The upload request was not allowed.", 403);
  }

  try {
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        if (!isDemoPathname(pathname)) {
          throw new Error("Only .dem replay uploads are allowed.");
        }

        return {
          allowedContentTypes: ["application/octet-stream"],
          maximumSizeInBytes: REPLAY_BLOB_MAX_BYTES,
          addRandomSuffix: true,
          cacheControlMaxAge: 60,
        };
      },
    });
    return Response.json(result);
  } catch {
    return errorResponse("The replay upload could not be authorized.", 400);
  }
}
