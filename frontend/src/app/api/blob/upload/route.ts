import { issueSignedToken } from "@vercel/blob";
import {
  handleUploadPresigned,
  type HandleUploadPresignedBody,
} from "@vercel/blob/client";

const REPLAY_BLOB_MAX_BYTES = 1024 * 1024 * 1024;
const TEMPORARY_REPLAY_PREFIX = "uploads/";
const TOKEN_REQUEST_TYPE = "blob.generate-presigned-url";

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
  return (
    pathname.startsWith(TEMPORARY_REPLAY_PREFIX) &&
    pathname.toLowerCase().endsWith(".dem")
  );
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
  const body = rawBody as HandleUploadPresignedBody;

  if (body.type === TOKEN_REQUEST_TYPE && !isSameOrigin(request)) {
    return errorResponse("The upload request was not allowed.", 403);
  }

  try {
    const result = await handleUploadPresigned({
      body,
      request,
      getSignedToken: async (pathname) => {
        if (!isDemoPathname(pathname)) {
          throw new Error("Only .dem replay uploads are allowed.");
        }

        const token = await issueSignedToken({
          pathname,
          operations: ["put"],
          allowedContentTypes: ["application/octet-stream"],
          maximumSizeInBytes: REPLAY_BLOB_MAX_BYTES,
        });

        return {
          token,
          urlOptions: {
            allowedContentTypes: ["application/octet-stream"],
            maximumSizeInBytes: REPLAY_BLOB_MAX_BYTES,
            addRandomSuffix: true,
            cacheControlMaxAge: 60,
          },
        };
      },
    });
    return Response.json(result);
  } catch (error: unknown) {
    console.error("[api/blob/upload] authorization failed", {
      name: error instanceof Error ? error.name : "UnknownError",
      message: error instanceof Error ? error.message : "Unknown Blob authorization error",
    });
    return errorResponse("The replay upload could not be authorized.", 400);
  }
}
