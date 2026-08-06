import { afterEach, describe, expect, it, vi } from "vitest";

const handleUploadMock = vi.hoisted(() => vi.fn());

vi.mock("@vercel/blob/client", () => ({ handleUpload: handleUploadMock }));

import { POST } from "@/app/api/blob/upload/route";

function uploadRequest(body: unknown, origin?: string): Request {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (origin !== undefined) {
    headers.set("Origin", origin);
  }
  return new Request("https://redecide.example/api/blob/upload", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  handleUploadMock.mockReset();
});

describe("Vercel Blob upload route", () => {
  it("stays unavailable when the frontend uses direct local uploads", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "direct");

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-client-token",
          payload: { pathname: "replays/match.dem", multipart: false, clientPayload: null },
        },
        "https://redecide.example",
      ),
    );

    expect(response.status).toBe(404);
    expect(handleUploadMock).not.toHaveBeenCalled();
  });

  it("rejects cross-origin requests for upload tokens", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-client-token",
          payload: { pathname: "replays/match.dem", multipart: false, clientPayload: null },
        },
        "https://attacker.example",
      ),
    );

    expect(response.status).toBe(403);
    expect(handleUploadMock).not.toHaveBeenCalled();
  });

  it("issues a bounded token configuration for same-origin .dem uploads", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    handleUploadMock.mockResolvedValue({
      type: "blob.generate-client-token",
      clientToken: "test-token",
    });

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-client-token",
          payload: { pathname: "replays/match.dem", multipart: true, clientPayload: null },
        },
        "https://redecide.example",
      ),
    );

    expect(response.status).toBe(200);
    const options = handleUploadMock.mock.calls[0]?.[0] as {
      onBeforeGenerateToken: (pathname: string) => Promise<Record<string, unknown>>;
    };
    await expect(options.onBeforeGenerateToken("replays/match.dem")).resolves.toEqual({
      allowedContentTypes: ["application/octet-stream"],
      maximumSizeInBytes: 1024 * 1024 * 1024,
      addRandomSuffix: true,
      cacheControlMaxAge: 60,
    });
    await expect(options.onBeforeGenerateToken("replays/match.zip")).rejects.toThrow(
      "Only .dem replay uploads are allowed.",
    );
  });

  it("allows Vercel's completion callback and returns safe failures", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    handleUploadMock
      .mockResolvedValueOnce({ type: "blob.upload-completed", response: "ok" })
      .mockRejectedValueOnce(new Error("private token detail"));
    const callback = {
      type: "blob.upload-completed",
      payload: {
        blob: { url: "https://store.public.blob.vercel-storage.com/replays/match.dem" },
      },
    };

    await expect(POST(uploadRequest(callback))).resolves.toMatchObject({ status: 200 });
    const failed = await POST(
      uploadRequest(
        {
          type: "blob.generate-client-token",
          payload: { pathname: "replays/match.dem", multipart: false, clientPayload: null },
        },
        "https://redecide.example",
      ),
    );

    expect(failed.status).toBe(400);
    await expect(failed.json()).resolves.toEqual({
      error: "The replay upload could not be authorized.",
    });
  });
});
