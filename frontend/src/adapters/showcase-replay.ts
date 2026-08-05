import { showcaseReplaySchema, type ShowcaseReplay } from "@/domain/replay-viewer";

export const SHOWCASE_REPLAY_URL = "/replays/mirage-showcase.replay.json";
let cachedShowcaseReplay: ShowcaseReplay | undefined;

export class ShowcaseReplayError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ShowcaseReplayError";
  }
}

export async function getShowcaseReplay(signal?: AbortSignal): Promise<ShowcaseReplay> {
  if (cachedShowcaseReplay) {
    return cachedShowcaseReplay;
  }

  let response: Response;
  try {
    response = await fetch(SHOWCASE_REPLAY_URL, { signal });
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ShowcaseReplayError("The Mirage showcase could not be loaded.");
  }

  if (!response.ok) {
    throw new ShowcaseReplayError("The Mirage showcase could not be loaded.");
  }

  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new ShowcaseReplayError("The Mirage showcase data is not valid JSON.");
  }

  const parsed = showcaseReplaySchema.safeParse(value);
  if (!parsed.success) {
    throw new ShowcaseReplayError("The Mirage showcase data did not match the replay format.");
  }
  cachedShowcaseReplay = parsed.data;
  return cachedShowcaseReplay;
}
