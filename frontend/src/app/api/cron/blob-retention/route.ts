import {
  del,
  get,
  list,
  type ListBlobResultBlob,
} from "@vercel/blob";

const DAY_MS = 24 * 60 * 60 * 1000;
const DEFAULT_FAILED_ANALYSIS_DAYS = 1;
const DEFAULT_ANALYSIS_DAYS = 14;
const DEFAULT_REPLAY_DAYS = 30;
const DEFAULT_MAX_SCANNED_BLOBS = 5_000;
const DEFAULT_MAX_DELETED_BLOBS = 500;
const LIST_PAGE_SIZE = 1_000;

type BlobAccess = "public" | "private";
type ArtifactGroup = {
  id: string;
  blobs: ListBlobResultBlob[];
  latestUploadMs: number;
};

type RetentionSummary = {
  scanned_blobs: number;
  eligible_blobs: number;
  eligible_analysis_jobs: number;
  eligible_replays: number;
  deleted_blobs: number;
  deleted_analysis_jobs: number;
  deleted_replays: number;
  kept_pinned_replays: number;
  inspection_errors: number;
  deletion_limit_reached: boolean;
  dry_run: boolean;
};

export const runtime = "nodejs";
export const maxDuration = 60;

function positiveInteger(name: string, fallback: number, maximum: number): number {
  const configured = process.env[name];
  if (configured === undefined || configured.trim() === "") {
    return fallback;
  }
  const parsed = Number(configured);
  return Number.isSafeInteger(parsed) && parsed > 0 && parsed <= maximum
    ? parsed
    : fallback;
}

function configuredPrefix(name: string, fallback: string): string {
  const value = (process.env[name] ?? fallback).replace(/^\/+|\/+$/g, "");
  return value || fallback;
}

function configuredAccess(): BlobAccess {
  return process.env.REDECIDE_BLOB_ACCESS === "private" ? "private" : "public";
}

async function listPrefix(prefix: string, limit: number): Promise<ListBlobResultBlob[]> {
  const blobs: ListBlobResultBlob[] = [];
  let cursor: string | undefined;

  while (blobs.length < limit) {
    const page = await list({
      prefix: `${prefix}/`,
      limit: Math.min(LIST_PAGE_SIZE, limit - blobs.length),
      ...(cursor ? { cursor } : {}),
    });
    blobs.push(...page.blobs);
    if (!page.hasMore || !page.cursor) {
      break;
    }
    cursor = page.cursor;
  }

  return blobs;
}

function groupArtifacts(
  blobs: ListBlobResultBlob[],
  prefix: string,
  validId: (value: string) => boolean,
  filenames: ReadonlySet<string>,
): ArtifactGroup[] {
  const groups = new Map<string, ListBlobResultBlob[]>();
  for (const blob of blobs) {
    const parts = blob.pathname.split("/");
    if (
      parts.length !== 3 ||
      parts[0] !== prefix ||
      !validId(parts[1]) ||
      !filenames.has(parts[2])
    ) {
      continue;
    }
    const current = groups.get(parts[1]) ?? [];
    current.push(blob);
    groups.set(parts[1], current);
  }

  return [...groups.entries()]
    .map(([id, groupBlobs]) => ({
      id,
      blobs: groupBlobs,
      latestUploadMs: Math.max(
        ...groupBlobs.map(({ uploadedAt }) => uploadedAt.getTime()),
      ),
    }))
    .sort((left, right) => left.latestUploadMs - right.latestUploadMs);
}

async function readJson(
  pathname: string | undefined,
  access: BlobAccess,
): Promise<Record<string, unknown> | null> {
  if (!pathname) {
    return null;
  }
  const result = await get(pathname, { access, useCache: false });
  if (result === null || result.statusCode !== 200) {
    return null;
  }
  const payload: unknown = await new Response(result.stream).json();
  return payload !== null && typeof payload === "object"
    ? (payload as Record<string, unknown>)
    : null;
}

function groupPath(group: ArtifactGroup, filename: string): string | undefined {
  return group.blobs.find(({ pathname }) => pathname.endsWith(`/${filename}`))
    ?.pathname;
}

function isPinnedSample(payload: Record<string, unknown> | null): boolean {
  const metadata = payload?._sample_cache;
  return (
    metadata !== null &&
    typeof metadata === "object" &&
    "pinned" in metadata &&
    metadata.pinned === true
  );
}

async function retentionCandidates(nowMs: number): Promise<{
  paths: string[];
  analysisJobs: number;
  replays: number;
  pinnedReplays: number;
  inspectionErrors: number;
  scannedBlobs: number;
  limitReached: boolean;
}> {
  const analysisPrefix = configuredPrefix(
    "REDECIDE_BLOB_ANALYSIS_PREFIX",
    "analysis",
  );
  const replayPrefix = configuredPrefix("REDECIDE_BLOB_REPLAY_PREFIX", "replays");
  const maxScanned = positiveInteger(
    "REDECIDE_RETENTION_MAX_SCANNED_BLOBS",
    DEFAULT_MAX_SCANNED_BLOBS,
    20_000,
  );
  const maxDeleted = positiveInteger(
    "REDECIDE_RETENTION_MAX_DELETED_BLOBS",
    DEFAULT_MAX_DELETED_BLOBS,
    1_000,
  );
  const failedCutoff =
    nowMs -
    positiveInteger(
      "REDECIDE_FAILED_ANALYSIS_RETENTION_DAYS",
      DEFAULT_FAILED_ANALYSIS_DAYS,
      365,
    ) *
      DAY_MS;
  const analysisCutoff =
    nowMs -
    positiveInteger(
      "REDECIDE_ANALYSIS_RETENTION_DAYS",
      DEFAULT_ANALYSIS_DAYS,
      3_650,
    ) *
      DAY_MS;
  const replayCutoff =
    nowMs -
    positiveInteger(
      "REDECIDE_REPLAY_RETENTION_DAYS",
      DEFAULT_REPLAY_DAYS,
      3_650,
    ) *
      DAY_MS;
  const access = configuredAccess();
  const [analysisBlobs, replayBlobs] = await Promise.all([
    listPrefix(analysisPrefix, maxScanned),
    listPrefix(replayPrefix, maxScanned),
  ]);
  const analysisGroups = groupArtifacts(
    analysisBlobs,
    analysisPrefix,
    (value) => /^[A-Za-z0-9._%~-]{1,200}$/.test(value),
    new Set(["state.json", "result.json"]),
  );
  const replayGroups = groupArtifacts(
    replayBlobs,
    replayPrefix,
    (value) => /^[0-9a-f]{32}$/.test(value),
    new Set(["manifest.json", "coaching.json", "visualization.json"]),
  );

  const paths: string[] = [];
  let analysisJobs = 0;
  let replays = 0;
  let pinnedReplays = 0;
  let inspectionErrors = 0;
  let limitReached = false;

  for (const group of analysisGroups) {
    if (group.latestUploadMs > failedCutoff) {
      continue;
    }
    try {
      const state = await readJson(groupPath(group, "state.json"), access);
      const cutoff = state?.status === "failed" ? failedCutoff : analysisCutoff;
      if (group.latestUploadMs > cutoff) {
        continue;
      }
    } catch {
      inspectionErrors += 1;
      continue;
    }
    if (paths.length + group.blobs.length > maxDeleted) {
      limitReached = true;
      break;
    }
    paths.push(...group.blobs.map(({ pathname }) => pathname));
    analysisJobs += 1;
  }

  for (const group of replayGroups) {
    if (group.latestUploadMs > replayCutoff) {
      continue;
    }
    try {
      const coaching = await readJson(groupPath(group, "coaching.json"), access);
      if (isPinnedSample(coaching)) {
        pinnedReplays += 1;
        continue;
      }
    } catch {
      inspectionErrors += 1;
      continue;
    }
    if (paths.length + group.blobs.length > maxDeleted) {
      limitReached = true;
      break;
    }
    paths.push(...group.blobs.map(({ pathname }) => pathname));
    replays += 1;
  }

  return {
    paths,
    analysisJobs,
    replays,
    pinnedReplays,
    inspectionErrors,
    scannedBlobs: analysisBlobs.length + replayBlobs.length,
    limitReached,
  };
}

export async function GET(request: Request): Promise<Response> {
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return Response.json({ error: "Blob retention is not configured." }, { status: 503 });
  }
  if (request.headers.get("authorization") !== `Bearer ${cronSecret}`) {
    return Response.json({ error: "Unauthorized." }, { status: 401 });
  }

  try {
    const candidates = await retentionCandidates(Date.now());
    const dryRun = process.env.REDECIDE_RETENTION_DRY_RUN === "true";
    if (!dryRun && candidates.paths.length > 0) {
      await del(candidates.paths);
    }
    const summary: RetentionSummary = {
      scanned_blobs: candidates.scannedBlobs,
      eligible_blobs: candidates.paths.length,
      eligible_analysis_jobs: candidates.analysisJobs,
      eligible_replays: candidates.replays,
      deleted_blobs: dryRun ? 0 : candidates.paths.length,
      deleted_analysis_jobs: dryRun ? 0 : candidates.analysisJobs,
      deleted_replays: dryRun ? 0 : candidates.replays,
      kept_pinned_replays: candidates.pinnedReplays,
      inspection_errors: candidates.inspectionErrors,
      deletion_limit_reached: candidates.limitReached,
      dry_run: dryRun,
    };
    console.info("[api/cron/blob-retention] completed", summary);
    return Response.json(summary);
  } catch (error: unknown) {
    console.error("[api/cron/blob-retention] failed", {
      name: error instanceof Error ? error.name : "UnknownError",
    });
    return Response.json({ error: "Blob retention failed." }, { status: 502 });
  }
}
