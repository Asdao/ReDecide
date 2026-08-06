import { afterEach, describe, expect, it, vi } from "vitest";

const { handleUploadPresignedMock, issueSignedTokenMock } = vi.hoisted(() => ({
  handleUploadPresignedMock: vi.fn(),
  issueSignedTokenMock: vi.fn(),
}));

vi.mock("@vercel/blob", () => ({ issueSignedToken: issueSignedTokenMock }));
vi.mock("@vercel/blob/client", () => ({
  handleUploadPresigned: handleUploadPresignedMock,
}));

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
  handleUploadPresignedMock.mockReset();
  issueSignedTokenMock.mockReset();
});

describe("Vercel Blob upload route", () => {
  it("stays unavailable when the frontend uses direct local uploads", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "direct");

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-presigned-url",
          payload: { pathname: "replays/match.dem", multipart: false, clientPayload: null },
        },
        "https://redecide.example",
      ),
    );

    expect(response.status).toBe(404);
    expect(handleUploadPresignedMock).not.toHaveBeenCalled();
  });

  it("rejects cross-origin requests for upload tokens", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-presigned-url",
          payload: { pathname: "replays/match.dem", multipart: false, clientPayload: null },
        },
        "https://attacker.example",
      ),
    );

    expect(response.status).toBe(403);
    expect(handleUploadPresignedMock).not.toHaveBeenCalled();
  });

  it("issues a bounded token configuration for same-origin .dem uploads", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    handleUploadPresignedMock.mockResolvedValue({
      type: "blob.generate-presigned-url",
      presignedUrlPayload: { delegationToken: "delegation", signature: "signature", params: {} },
    });
    issueSignedTokenMock.mockResolvedValue({
      delegationToken: "delegation",
      clientSigningToken: "signing-token",
      validUntil: Date.now() + 60_000,
    });

    const response = await POST(
      uploadRequest(
        {
          type: "blob.generate-presigned-url",
          payload: { pathname: "replays/match.dem", multipart: true, clientPayload: null },
        },
        "https://redecide.example",
      ),
    );

    expect(response.status).toBe(200);
    const options = handleUploadPresignedMock.mock.calls[0]?.[0] as {
      getSignedToken: (pathname: string) => Promise<Record<string, unknown>>;
    };
    await expect(options.getSignedToken("replays/match.dem")).resolves.toEqual({
      token: {
        delegationToken: "delegation",
        clientSigningToken: "signing-token",
        validUntil: expect.any(Number),
      },
      urlOptions: {
        allowedContentTypes: ["application/octet-stream"],
        maximumSizeInBytes: 1024 * 1024 * 1024,
        addRandomSuffix: true,
        cacheControlMaxAge: 60,
      },
    });
    expect(issueSignedTokenMock).toHaveBeenCalledWith({
      pathname: "replays/match.dem",
      operations: ["put"],
      allowedContentTypes: ["application/octet-stream"],
      maximumSizeInBytes: 1024 * 1024 * 1024,
    });
    await expect(options.getSignedToken("replays/match.zip")).rejects.toThrow(
      "Only .dem replay uploads are allowed.",
    );
  });

  it("allows Vercel's completion callback and returns safe failures", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    handleUploadPresignedMock
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
          type: "blob.generate-presigned-url",
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
