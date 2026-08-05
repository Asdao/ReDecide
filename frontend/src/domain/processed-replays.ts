export type ProcessedReplaySummary = {
  replayId: string;
  displayName: string;
  description: string;
  map: string;
  rounds: number;
  players: number;
  replayUrl: string;
  analysisAvailable: boolean;
};

export const PROCESSED_REPLAYS: readonly ProcessedReplaySummary[] = [
  {
    replayId: "mirage-showcase",
    displayName: "Mirage showcase",
    description: "A sanitized 30-round replay prepared for the tactical viewer.",
    map: "de_mirage",
    rounds: 30,
    players: 10,
    replayUrl: "/replays/mirage-showcase.replay.json",
    analysisAvailable: false,
  },
  {
    replayId: "inferno-processed",
    displayName: "Inferno processed replay",
    description: "A backend-generated 29-round replay with named player perspectives.",
    map: "de_inferno",
    rounds: 29,
    players: 10,
    replayUrl: "/replays/inferno-processed.replay.json",
    analysisAvailable: false,
  },
] as const;

export function processedReplayById(replayId: string | undefined) {
  return PROCESSED_REPLAYS.find((replay) => replay.replayId === replayId);
}
