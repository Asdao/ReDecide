import { afterEach, describe, expect, it, vi } from "vitest";

const { deleteBlobMock, getBlobMock, listBlobMock } = vi.hoisted(() => ({
  deleteBlobMock: vi.fn(),
  getBlobMock: vi.fn(),
  listBlobMock: vi.fn(),
}));

vi.mock("@vercel/blob", () => ({
  del: deleteBlobMock,
  get: getBlobMock,
  list: listBlobMock,
}));

import { GET } from "@/app/api/cron/blob-retention/route";

const NOW = new Date("2026-08-07T12:00:00.000Z");

function cronRequest(secret = "retention-secret"): Request {
  return new Request("https://redecide.example/api/cron/blob-retention", {
    headers: { Authorization: `Bearer ${secret}` },
  });
}

function blob(pathname: string, ageHours: number) {
  const url = `https://store.public.blob.vercel-storage.com/${pathname}`;
  return {
    url,
    downloadUrl: url,
    pathname,
    size: 100,
    uploadedAt: new Date(NOW.getTime() - ageHours * 60 * 60 * 1_000),
    etag: `etag-${pathname}`,
  };
}

function jsonBlob(payload: unknown) {
  const body = JSON.stringify(payload);
  return {
    statusCode: 200,
    stream: new Response(body).body,
    headers: new Headers({ "content-type": "application/json" }),
    blob: {
      url: "https://store.public.blob.vercel-storage.com/artifact.json",
      downloadUrl: "https://store.public.blob.vercel-storage.com/artifact.json",
      pathname: "artifact.json",
      contentDisposition: "inline",
      cacheControl: "public, max-age=0",
      uploadedAt: NOW,
      etag: "etag-artifact",
      contentType: "application/json",
      size: body.length,
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  deleteBlobMock.mockReset();
  getBlobMock.mockReset();
  listBlobMock.mockReset();
});

describe("server-only Vercel Blob retention route", () => {
  it("fails closed without the configured cron secret", async () => {
    const unconfigured = await GET(cronRequest());
    expect(unconfigured.status).toBe(503);

    vi.stubEnv("CRON_SECRET", "retention-secret");
    const unauthorized = await GET(cronRequest("wrong-secret"));
    expect(unauthorized.status).toBe(401);
    expect(listBlobMock).not.toHaveBeenCalled();
    expect(deleteBlobMock).not.toHaveBeenCalled();
  });

  it("deletes expired JSON groups and preserves recent and pinned sample data", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    vi.stubEnv("CRON_SECRET", "retention-secret");
    vi.stubEnv("REDECIDE_BLOB_ACCESS", "private");

    const failedId = "failed-job";
    const completeId = "complete-job";
    const recentId = "recent-job";
    const unpinnedReplay = "a".repeat(32);
    const pinnedReplay = "b".repeat(32);
    const recentReplay = "c".repeat(32);
    const analysisBlobs = [
      blob(`analysis/${failedId}/state.json`, 48),
      blob(`analysis/${failedId}/result.json`, 48),
      blob(`analysis/${completeId}/state.json`, 15 * 24),
      blob(`analysis/${completeId}/result.json`, 15 * 24),
      blob(`analysis/${recentId}/state.json`, 12),
      blob(`analysis/${recentId}/result.json`, 12),
    ];
    const replayBlobs = [
      ...["manifest.json", "coaching.json", "visualization.json"].map((name) =>
        blob(`replays/${unpinnedReplay}/${name}`, 31 * 24),
      ),
      ...["manifest.json", "coaching.json", "visualization.json"].map((name) =>
        blob(`replays/${pinnedReplay}/${name}`, 31 * 24),
      ),
      ...["manifest.json", "coaching.json", "visualization.json"].map((name) =>
        blob(`replays/${recentReplay}/${name}`, 12),
      ),
    ];
    listBlobMock.mockImplementation(async ({ prefix }: { prefix: string }) => ({
      blobs: prefix === "analysis/" ? analysisBlobs : replayBlobs,
      hasMore: false,
    }));
    getBlobMock.mockImplementation(async (pathname: string) => {
      if (pathname === `analysis/${failedId}/state.json`) {
        return jsonBlob({ status: "failed" });
      }
      if (pathname === `analysis/${completeId}/state.json`) {
        return jsonBlob({ status: "complete" });
      }
      if (pathname === `replays/${pinnedReplay}/coaching.json`) {
        return jsonBlob({ _sample_cache: { pinned: true } });
      }
      return jsonBlob({});
    });
    deleteBlobMock.mockResolvedValue(undefined);

    const response = await GET(cronRequest());

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      scanned_blobs: 15,
      eligible_blobs: 7,
      eligible_analysis_jobs: 2,
      eligible_replays: 1,
      deleted_blobs: 7,
      deleted_analysis_jobs: 2,
      deleted_replays: 1,
      kept_pinned_replays: 1,
      inspection_errors: 0,
      deletion_limit_reached: false,
      dry_run: false,
    });
    expect(deleteBlobMock).toHaveBeenCalledOnce();
    const deleted = deleteBlobMock.mock.calls[0][0] as string[];
    expect(deleted).toHaveLength(7);
    expect(deleted).toContain(`analysis/${failedId}/state.json`);
    expect(deleted).toContain(`analysis/${completeId}/result.json`);
    expect(deleted).toContain(`replays/${unpinnedReplay}/coaching.json`);
    expect(deleted).not.toContain(`analysis/${recentId}/state.json`);
    expect(deleted).not.toContain(`replays/${pinnedReplay}/coaching.json`);
    expect(getBlobMock).toHaveBeenCalledWith(
      `replays/${pinnedReplay}/coaching.json`,
      { access: "private", useCache: false },
    );
  });

  it("supports a dry run without deleting eligible blobs", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    vi.stubEnv("CRON_SECRET", "retention-secret");
    vi.stubEnv("REDECIDE_RETENTION_DRY_RUN", "true");
    const failedId = "failed-job";
    listBlobMock.mockImplementation(async ({ prefix }: { prefix: string }) => ({
      blobs:
        prefix === "analysis/"
          ? [
              blob(`analysis/${failedId}/state.json`, 48),
              blob(`analysis/${failedId}/result.json`, 48),
            ]
          : [],
      hasMore: false,
    }));
    getBlobMock.mockResolvedValue(jsonBlob({ status: "failed" }));

    const response = await GET(cronRequest());

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      dry_run: true,
      eligible_blobs: 2,
      eligible_analysis_jobs: 1,
      eligible_replays: 0,
      deleted_blobs: 0,
    });
    expect(deleteBlobMock).not.toHaveBeenCalled();
  });

  it("returns a safe error when Blob listing fails", async () => {
    vi.stubEnv("CRON_SECRET", "retention-secret");
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    listBlobMock.mockRejectedValue(new Error("private provider detail"));

    const response = await GET(cronRequest());

    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toEqual({
      error: "Blob retention failed.",
    });
    expect(deleteBlobMock).not.toHaveBeenCalled();
  });
});
