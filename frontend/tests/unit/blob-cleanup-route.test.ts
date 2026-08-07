import { afterEach, describe, expect, it, vi } from "vitest";

const deleteBlobMock = vi.hoisted(() => vi.fn());

vi.mock("@vercel/blob", () => ({ del: deleteBlobMock }));

import { POST } from "@/app/api/blob/cleanup/route";

const TEMPORARY_BLOB_URL =
  "https://store123.public.blob.vercel-storage.com/uploads/match-abc.dem";

function cleanupRequest(body: unknown, origin?: string): Request {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (origin !== undefined) {
    headers.set("Origin", origin);
  }
  return new Request("https://redecide.example/api/blob/cleanup", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  deleteBlobMock.mockReset();
});

describe("Vercel Blob cleanup route", () => {
  it("stays unavailable when Blob replay uploads are disabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "direct");

    const response = await POST(
      cleanupRequest({ url: TEMPORARY_BLOB_URL }, "https://redecide.example"),
    );

    expect(response.status).toBe(404);
    expect(deleteBlobMock).not.toHaveBeenCalled();
  });

  it("rejects cross-origin deletion requests", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");

    const response = await POST(
      cleanupRequest({ url: TEMPORARY_BLOB_URL }, "https://attacker.example"),
    );

    expect(response.status).toBe(403);
    expect(deleteBlobMock).not.toHaveBeenCalled();
  });

  it("deletes only public temporary .dem objects", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    deleteBlobMock.mockResolvedValue(undefined);

    const response = await POST(
      cleanupRequest({ url: TEMPORARY_BLOB_URL }, "https://redecide.example"),
    );

    expect(response.status).toBe(204);
    expect(deleteBlobMock).toHaveBeenCalledWith(TEMPORARY_BLOB_URL);

    for (const url of [
      "https://example.com/uploads/match.dem",
      "https://store123.public.blob.vercel-storage.com/replays/match.dem",
      "https://store123.public.blob.vercel-storage.com/uploads/match.zip",
    ]) {
      const rejected = await POST(
        cleanupRequest({ url }, "https://redecide.example"),
      );
      expect(rejected.status).toBe(400);
    }
    expect(deleteBlobMock).toHaveBeenCalledTimes(1);
  });

  it("returns a safe error when deletion fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_REPLAY_UPLOAD_MODE", "blob");
    deleteBlobMock.mockRejectedValue(new Error("private provider detail"));

    const response = await POST(
      cleanupRequest({ url: TEMPORARY_BLOB_URL }, "https://redecide.example"),
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: "The temporary replay could not be deleted.",
    });
  });
});
