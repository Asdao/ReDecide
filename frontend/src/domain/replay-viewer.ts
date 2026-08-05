import { z } from "zod";

const requiredString = z.string().trim().min(1);
const nonnegativeInteger = z.number().int().nonnegative();

const showcasePlayerSchema = z
  .object({
    player_id: requiredString,
    display_name: requiredString.nullable(),
    sides: z.array(requiredString),
  })
  .strict();

const showcaseRoundSchema = z
  .object({
    round_num: nonnegativeInteger,
    start: nonnegativeInteger,
    freeze_end: nonnegativeInteger.nullable().optional(),
    end: nonnegativeInteger,
    official_end: nonnegativeInteger.nullable().optional(),
    winner: requiredString.nullable().optional(),
    reason: requiredString.nullable().optional(),
    bomb_plant: nonnegativeInteger.nullable().optional(),
    bomb_site: requiredString.nullable().optional(),
  })
  .passthrough();

const showcaseEventSchema = z
  .object({
    event_id: requiredString,
    event: requiredString,
    tick: nonnegativeInteger,
    round_num: nonnegativeInteger,
    attacker_id: requiredString.nullable().optional(),
    victim_id: requiredString.nullable().optional(),
    player_id: requiredString.nullable().optional(),
    weapon: z.string().nullable().optional(),
    headshot: z.boolean().optional(),
    damage_health: z.number().optional(),
    bomb_site: requiredString.nullable().optional(),
  })
  .passthrough();

const showcaseSnapshotSchema = z
  .object({
    tick: nonnegativeInteger,
    round_num: nonnegativeInteger,
    player_id: requiredString,
    display_name: requiredString.nullable(),
    side: z.enum(["ct", "t"]),
    X: z.number(),
    Y: z.number(),
    Z: z.number(),
    health: z.number(),
    armor: z.number(),
    alive: z.boolean(),
    has_defuser: z.boolean(),
    place: z.string().nullable(),
  })
  .passthrough();

export const showcaseReplaySchema = z
  .object({
    schema_version: z.literal("replay_visualization_v1"),
    replay_id: requiredString,
    source: requiredString,
    map: z
      .object({
        name: z.literal("de_mirage"),
        tick_rate: z.number().positive(),
      })
      .strict(),
    players: z.array(showcasePlayerSchema).min(1),
    rounds: z.array(showcaseRoundSchema).min(1),
    events: z.array(showcaseEventSchema),
    ticks: z.array(showcaseSnapshotSchema).min(1),
  })
  .strict();

export type ShowcaseReplay = z.infer<typeof showcaseReplaySchema>;
export type ShowcasePlayer = ShowcaseReplay["players"][number];
export type ShowcaseRound = ShowcaseReplay["rounds"][number];
export type ShowcaseEvent = ShowcaseReplay["events"][number];
export type ShowcaseSnapshot = ShowcaseReplay["ticks"][number];

export type ReplayFrame = {
  tick: number;
  snapshots: ShowcaseSnapshot[];
};

export const MIRAGE_OVERVIEW = {
  positionX: -3230,
  positionY: 1713,
  scale: 5,
  imageSize: 1024,
} as const;

export function worldToMirageRadar(x: number, y: number) {
  const { positionX, positionY, scale, imageSize } = MIRAGE_OVERVIEW;
  return {
    left: ((x - positionX) / (scale * imageSize)) * 100,
    top: ((positionY - y) / (scale * imageSize)) * 100,
  };
}

export function buildReplayFrames(snapshots: ShowcaseSnapshot[]): ReplayFrame[] {
  const sorted = [...snapshots].sort(
    (left, right) => left.tick - right.tick || left.player_id.localeCompare(right.player_id),
  );
  const frames: ReplayFrame[] = [];

  for (const snapshot of sorted) {
    const current = frames.at(-1);
    if (!current || current.tick !== snapshot.tick) {
      frames.push({ tick: snapshot.tick, snapshots: [snapshot] });
    } else {
      current.snapshots.push(snapshot);
    }
  }

  return frames;
}

function frameIndexAtTick(frames: ReplayFrame[], tick: number): number {
  if (frames.length === 0 || tick < frames[0].tick) {
    return -1;
  }

  let low = 0;
  let high = frames.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (frames[middle].tick <= tick) {
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return high;
}

export function frameAtTick(frames: ReplayFrame[], tick: number): ReplayFrame | undefined {
  const index = frameIndexAtTick(frames, tick);
  return index >= 0 ? frames[index] : undefined;
}

export function interpolatedSnapshotsAtTick(
  frames: ReplayFrame[],
  tick: number,
): ShowcaseSnapshot[] {
  const currentIndex = frameIndexAtTick(frames, tick);
  if (currentIndex < 0) {
    return [];
  }

  const current = frames[currentIndex];
  const next = frames[currentIndex + 1];
  if (!next || next.tick <= current.tick) {
    return current.snapshots;
  }

  const progress = Math.min(1, Math.max(0, (tick - current.tick) / (next.tick - current.tick)));
  const nextByPlayer = new Map(next.snapshots.map((snapshot) => [snapshot.player_id, snapshot]));

  return current.snapshots.map((snapshot) => {
    const nextSnapshot = nextByPlayer.get(snapshot.player_id);
    if (!nextSnapshot || nextSnapshot.round_num !== snapshot.round_num) {
      return snapshot;
    }

    return {
      ...snapshot,
      X: snapshot.X + (nextSnapshot.X - snapshot.X) * progress,
      Y: snapshot.Y + (nextSnapshot.Y - snapshot.Y) * progress,
      Z: snapshot.Z + (nextSnapshot.Z - snapshot.Z) * progress,
    };
  });
}

export function roundAtTick(rounds: ShowcaseRound[], tick: number): ShowcaseRound | undefined {
  for (let index = rounds.length - 1; index >= 0; index -= 1) {
    const round = rounds[index];
    const end = round.official_end ?? round.end;
    if (tick >= round.start && tick <= end) {
      return round;
    }
  }
  return undefined;
}

export function formatReplayTime(tick: number, firstTick: number, tickRate: number): string {
  const seconds = Math.max(0, (tick - firstTick) / tickRate);
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.floor(seconds % 60);
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

export function playerDisplayName(player: ShowcasePlayer): string {
  return player.display_name ?? "Unnamed player";
}

export function playerTimelineEvents(
  events: ShowcaseEvent[],
  playerId: string,
): ShowcaseEvent[] {
  return events.filter(
    (event) =>
      (event.event === "damage" || event.event === "kill") &&
      event.victim_id === playerId,
  );
}

export function firstEventCrossed(
  events: ShowcaseEvent[],
  previousTick: number,
  nextTick: number,
): ShowcaseEvent | undefined {
  return events.find(
    (event) => event.tick > previousTick && event.tick <= nextTick,
  );
}
