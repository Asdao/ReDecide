import { afterEach, describe, expect, it, vi } from "vitest";

const { issueSignedTokenMock, presignUrlMock } = vi.hoisted(() => ({
  issueSignedTokenMock: vi.fn(),
  presignUrlMock: vi.fn(),
}));

vi.mock("@vercel/blob", () => ({
  issueSignedToken: issueSignedTokenMock,
  presignUrl: presignUrlMock,
}));

import { POST } from "@/app/service-internal/blob-artifacts/route";

function ticketRequest(body: unknown): Request {
  return new Request("https://frontend.internal/service-internal/blob-artifacts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  issueSignedTokenMock.mockReset();
  presignUrlMock.mockReset();
});

describe("private Blob artifact bridge", () => {
  it("issues an exact, bounded PUT URL for replay JSON", async () => {
    vi.stubEnv("REDECIDE_BLOB_ACCESS", "private");
    issueSignedTokenMock.mockResolvedValue({
      delegationToken: "delegation",
      clientSigningToken: "client-signing",
    });
    presignUrlMock.mockResolvedValue({ presignedUrl: "https://blob.example/signed-put" });

    const response = await POST(
      ticketRequest({
        operation: "put",
        pathname: "replays/0123456789abcdef0123456789abcdef/manifest.json",
        access: "private",
        contentType: "application/json",
        size: 2048,
      }),
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      url: "https://blob.example/signed-put",
      expiresAt: expect.any(Number),
    });
    expect(issueSignedTokenMock).toHaveBeenCalledWith({
      pathname: "replays/0123456789abcdef0123456789abcdef/manifest.json",
      operations: ["put"],
      validUntil: expect.any(Number),
      allowedContentTypes: ["application/json"],
      maximumSizeInBytes: 2048,
    });
    expect(presignUrlMock).toHaveBeenCalledWith(
      expect.objectContaining({ delegationToken: "delegation" }),
      expect.objectContaining({
        operation: "put",
        pathname: "replays/0123456789abcdef0123456789abcdef/manifest.json",
        access: "private",
        allowedContentTypes: ["application/json"],
        maximumSizeInBytes: 2048,
        allowOverwrite: true,
        addRandomSuffix: false,
      }),
    );
  });

  it("issues a GET-only URL for an encoded analysis identifier", async () => {
    issueSignedTokenMock.mockResolvedValue({
      delegationToken: "delegation",
      clientSigningToken: "client-signing",
    });
    presignUrlMock.mockResolvedValue({ presignedUrl: "https://blob.example/signed-get" });

    const response = await POST(
      ticketRequest({
        operation: "get",
        pathname: "analysis/analysis%2Fone/result.json",
        access: "public",
      }),
    );

    expect(response.status).toBe(200);
    const payload = await response.json();
    const signedUrl = new URL(payload.url);
    expect(`${signedUrl.origin}${signedUrl.pathname}`).toBe("https://blob.example/signed-get");
    expect(signedUrl.searchParams.get("redecide_cache_bust")).toMatch(
      /^[0-9a-f-]{36}$/,
    );
    expect(issueSignedTokenMock).toHaveBeenCalledWith({
      pathname: "analysis/analysis%2Fone/result.json",
      operations: ["get"],
      validUntil: expect.any(Number),
    });
    expect(presignUrlMock).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({
        operation: "get",
        pathname: "analysis/analysis%2Fone/result.json",
        access: "public",
      }),
    );
  });

  it.each([
    { operation: "delete", pathname: "replays/0123456789abcdef0123456789abcdef/manifest.json", access: "public" },
    { operation: "get", pathname: "uploads/match.dem", access: "public" },
    { operation: "get", pathname: "replays/0123456789abcdef0123456789abcdef/../../secret.json", access: "public" },
    { operation: "put", pathname: "analysis/job/state.json", access: "public", contentType: "text/plain", size: 1 },
    { operation: "put", pathname: "analysis/job/state.json", access: "public", contentType: "application/json", size: 128 * 1024 * 1024 + 1 },
    { operation: "get", pathname: "analysis/job/state.json", access: "private" },
  ])("rejects an unscoped or mismatched request: $operation $pathname", async (body) => {
    const response = await POST(ticketRequest(body));

    expect(response.status).toBe(400);
    expect(issueSignedTokenMock).not.toHaveBeenCalled();
  });

  it("does not expose provider failures in its response", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    issueSignedTokenMock.mockRejectedValue(new Error("secret provider detail"));

    const response = await POST(
      ticketRequest({
        operation: "get",
        pathname: "analysis/job/state.json",
        access: "public",
      }),
    );

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: "The Blob artifact request could not be authorized.",
    });
  });
});
