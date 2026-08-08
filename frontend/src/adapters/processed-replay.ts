import { normalizeBackendReplay, type ProcessedReplay } from "@/domain/replay-viewer";
import { processedReplayById } from "@/domain/processed-replays";
import { replayAnalysisResultSchema, type ReplayAnalysisResult } from "@/domain/replay";
import { isAbortError } from "@/lib/http";

const replayCache = new Map<string, ProcessedReplay>();
const analysisCache = new Map<string, ReplayAnalysisResult>();

export class ProcessedReplayError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProcessedReplayError";
  }
}

export async function getProcessedReplay(
  replayId: string | undefined,
  signal?: AbortSignal,
): Promise<ProcessedReplay> {
  const summary = processedReplayById(replayId);
  if (!summary) {
    throw new ProcessedReplayError("That processed replay is not available.");
  }

  const cached = replayCache.get(summary.replayId);
  if (cached) {
    return cached;
  }

  let response: Response;
  try {
    response = await fetch(summary.replayUrl, { signal });
  } catch (error: unknown) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ProcessedReplayError("The processed replay could not be loaded.");
  }

  if (!response.ok) {
    throw new ProcessedReplayError("The processed replay could not be loaded.");
  }

  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new ProcessedReplayError("The processed replay data is not valid JSON.");
  }

  try {
    const replay = normalizeBackendReplay(value);
    replayCache.set(summary.replayId, replay);
    return replay;
  } catch {
    throw new ProcessedReplayError("The processed replay data did not match the replay format.");
  }
}

export async function getProcessedReplayAnalysis(
  replayId: string | undefined,
  signal?: AbortSignal,
): Promise<ReplayAnalysisResult | undefined> {
  const summary = processedReplayById(replayId);
  if (!summary) {
    throw new ProcessedReplayError("That processed replay is not available.");
  }
  if (!summary.analysisUrl) {
    return undefined;
  }

  const cached = analysisCache.get(summary.replayId);
  if (cached) {
    return cached;
  }

  let response: Response;
  try {
    response = await fetch(summary.analysisUrl, { signal });
  } catch (error: unknown) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ProcessedReplayError("The saved replay analysis could not be loaded.");
  }

  if (!response.ok) {
    throw new ProcessedReplayError("The saved replay analysis could not be loaded.");
  }

  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new ProcessedReplayError("The saved replay analysis is not valid JSON.");
  }

  const parsed = replayAnalysisResultSchema.safeParse(value);
  if (!parsed.success) {
    throw new ProcessedReplayError("The saved replay analysis did not match the analysis format.");
  }
  const analyses = parsed.data.analyses?.length
    ? parsed.data.analyses
    : [{
        selected_decision: parsed.data.selected_decision,
        coach_analysis: parsed.data.coach_analysis,
      }];
  const analyzedPlayerIds = new Set(
    analyses.map(({ selected_decision }) => selected_decision.player_id),
  );
  const missingPlayer = parsed.data.players.find(
    ({ player_id, decision_ids }) => decision_ids.length > 0 && !analyzedPlayerIds.has(player_id),
  );
  if (missingPlayer) {
    throw new ProcessedReplayError("The saved replay analysis did not cover every player.");
  }

  analysisCache.set(summary.replayId, parsed.data);
  return parsed.data;
}
