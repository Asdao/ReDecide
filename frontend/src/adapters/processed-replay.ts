import { normalizeBackendReplay, type ProcessedReplay } from "@/domain/replay-viewer";
import { processedReplayById } from "@/domain/processed-replays";

const replayCache = new Map<string, ProcessedReplay>();

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
    if (error instanceof DOMException && error.name === "AbortError") {
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
