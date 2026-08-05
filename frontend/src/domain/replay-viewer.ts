import { z } from "zod";

const requiredString = z.string().trim().min(1);
const nonnegativeInteger = z.number().int().nonnegative();

const replayPlayerSchema = z
  .object({
    player_id: requiredString,
    display_name: requiredString.nullable(),
    sides: z.array(requiredString),
  })
  .strict();

const replayRoundSchema = z
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

const replayEventSchema = z
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
  .strict();

const replaySnapshotSchema = z
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
  .strict();

export const processedReplaySchema = z
  .object({
    schema_version: z.literal("replay_visualization_v1"),
    replay_id: requiredString,
    source: requiredString,
    map: z
      .object({
        name: requiredString,
        tick_rate: z.number().positive(),
      })
      .strict(),
    players: z.array(replayPlayerSchema).min(1),
    rounds: z.array(replayRoundSchema).min(1),
    events: z.array(replayEventSchema),
    ticks: z.array(replaySnapshotSchema).min(1),
  })
  .strict();

const backendTickSchema = z
  .object({
    tick: nonnegativeInteger,
    round_num: nonnegativeInteger,
    player_id: requiredString.optional(),
    display_name: requiredString.nullable().optional(),
    player_name: requiredString.optional(),
    name: requiredString.optional(),
    side: z.string(),
    X: z.number(),
    Y: z.number(),
    Z: z.number(),
    health: z.number(),
    armor: z.number().optional(),
    armor_value: z.number().optional(),
    alive: z.boolean().optional(),
    has_defuser: z.boolean().optional(),
    place: z.string().nullable().optional(),
  })
  .passthrough();

const backendEventSchema = z
  .object({
    event_id: requiredString.optional(),
    event: requiredString,
    tick: nonnegativeInteger,
    round_num: nonnegativeInteger.optional(),
    round: nonnegativeInteger.optional(),
  })
  .passthrough();

const backendReplaySchema = z
  .object({
    schema_version: z.literal("replay_visualization_v1"),
    replay_id: requiredString,
    source: requiredString,
    map: z
      .object({
        name: requiredString,
        tick_rate: z.number().positive(),
      })
      .strict(),
    players: z.array(replayPlayerSchema).min(1),
    rounds: z.array(replayRoundSchema).min(1),
    events: z.array(backendEventSchema),
    ticks: z.array(backendTickSchema).min(1),
  })
  .strict();

export type ProcessedReplay = z.infer<typeof processedReplaySchema>;
export type ReplayPlayer = ProcessedReplay["players"][number];
export type ReplayRound = ProcessedReplay["rounds"][number];
export type ReplayEvent = ProcessedReplay["events"][number];
export type ReplaySnapshot = ProcessedReplay["ticks"][number];

export type ReplayFrame = {
  tick: number;
  snapshots: ReplaySnapshot[];
};

export type RadarOverview = {
  positionX: number;
  positionY: number;
  scale: number;
  imageSize: number;
  image: string;
};

const RADAR_OVERVIEWS: Readonly<Record<string, RadarOverview>> = {
  de_ancient: { positionX: -2953, positionY: 2164, scale: 5, imageSize: 1024, image: "/radars/de_ancient.png" },
  de_anubis: { positionX: -2796, positionY: 3328, scale: 5.22, imageSize: 1024, image: "/radars/de_anubis.png" },
  de_dust2: { positionX: -2476, positionY: 3239, scale: 4.4, imageSize: 1024, image: "/radars/de_dust2.png" },
  de_inferno: { positionX: -2087, positionY: 3870, scale: 4.9, imageSize: 1024, image: "/radars/de_inferno.png" },
  de_mirage: { positionX: -3230, positionY: 1713, scale: 5, imageSize: 1024, image: "/radars/de_mirage.png" },
  de_nuke: { positionX: -3453, positionY: 2887, scale: 7, imageSize: 1024, image: "/radars/de_nuke.png" },
  de_overpass: { positionX: -4831, positionY: 1781, scale: 5.2, imageSize: 1024, image: "/radars/de_overpass.png" },
};

export function radarOverviewForMap(mapName: string): RadarOverview | undefined {
  return RADAR_OVERVIEWS[mapName];
}

export function worldToRadar(x: number, y: number, overview: RadarOverview) {
  const { positionX, positionY, scale, imageSize } = overview;
  return {
    left: ((x - positionX) / (scale * imageSize)) * 100,
    top: ((positionY - y) / (scale * imageSize)) * 100,
  };
}

function stringField(record: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function numberField(record: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return undefined;
}

function playerIdForEvent(
  event: Record<string, unknown>,
  playersById: ReadonlyMap<string, ReplayPlayer>,
  playersByName: ReadonlyMap<string, ReplayPlayer>,
  idKey: string,
  nameKey: string,
): string | undefined {
  const suppliedId = stringField(event, idKey);
  if (suppliedId && playersById.has(suppliedId)) {
    return suppliedId;
  }
  const suppliedName = stringField(event, nameKey);
  return suppliedName ? playersByName.get(suppliedName)?.player_id : undefined;
}

const renderedEventTypes = new Set(["damage", "kill", "plant", "defuse", "detonate"]);

export function normalizeBackendReplay(value: unknown): ProcessedReplay {
  const input = backendReplaySchema.parse(value);
  const playersById = new Map(input.players.map((player) => [player.player_id, player]));
  const playersByName = new Map(
    input.players.flatMap((player) =>
      player.display_name ? [[player.display_name, player] as const] : [],
    ),
  );

  const ticks = input.ticks.map((tick) => {
    const displayName = tick.display_name ?? tick.player_name ?? tick.name ?? null;
    const player =
      (tick.player_id ? playersById.get(tick.player_id) : undefined) ??
      (displayName ? playersByName.get(displayName) : undefined);
    if (!player) {
      throw new Error("A replay snapshot could not be matched to a listed player.");
    }

    const side = tick.side.toLowerCase();
    if (side !== "ct" && side !== "t") {
      throw new Error("A replay snapshot used an unsupported team side.");
    }

    return {
      tick: tick.tick,
      round_num: tick.round_num,
      player_id: player.player_id,
      display_name: displayName ?? player.display_name,
      side,
      X: tick.X,
      Y: tick.Y,
      Z: tick.Z,
      health: tick.health,
      armor: tick.armor ?? tick.armor_value ?? 0,
      alive: tick.alive ?? tick.health > 0,
      has_defuser: tick.has_defuser ?? false,
      place: tick.place ?? null,
    };
  });

  const eventOrdinals = new Map<string, number>();
  const events = input.events.flatMap((event) => {
    if (!renderedEventTypes.has(event.event)) {
      return [];
    }
    const record: Record<string, unknown> = event;
    const roundNum = event.round_num ?? event.round;
    if (roundNum === undefined) {
      return [];
    }

    const attackerId = playerIdForEvent(
      record,
      playersById,
      playersByName,
      "attacker_id",
      "attacker_name",
    );
    const victimId = playerIdForEvent(
      record,
      playersById,
      playersByName,
      "victim_id",
      "victim_name",
    );
    const playerId =
      playerIdForEvent(record, playersById, playersByName, "player_id", "name") ??
      playerIdForEvent(record, playersById, playersByName, "player_id", "player_name");
    const fingerprint = [event.event, roundNum, event.tick, attackerId, victimId, playerId]
      .filter((part) => part !== undefined)
      .join(":");
    const ordinal = eventOrdinals.get(fingerprint) ?? 0;
    eventOrdinals.set(fingerprint, ordinal + 1);

    return [{
      event_id: event.event_id ?? `${fingerprint}:${ordinal}`,
      event: event.event,
      tick: event.tick,
      round_num: roundNum,
      attacker_id: attackerId ?? null,
      victim_id: victimId ?? null,
      player_id: playerId ?? null,
      weapon: stringField(record, "weapon") ?? null,
      headshot: typeof record.headshot === "boolean" ? record.headshot : false,
      damage_health: numberField(record, "damage_health", "dmg_health_real", "dmg_health"),
      bomb_site: stringField(record, "bomb_site", "bombsite") ?? null,
    }];
  });

  return processedReplaySchema.parse({
    ...input,
    ticks,
    events,
  });
}

export function buildReplayFrames(snapshots: ReplaySnapshot[]): ReplayFrame[] {
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
): ReplaySnapshot[] {
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

export function roundAtTick(rounds: ReplayRound[], tick: number): ReplayRound | undefined {
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

export function playerDisplayName(player: ReplayPlayer): string {
  return player.display_name ?? "Unnamed player";
}

export function playerTimelineEvents(
  events: ReplayEvent[],
  playerId: string,
): ReplayEvent[] {
  return events.filter(
    (event) =>
      (event.event === "damage" || event.event === "kill") &&
      event.victim_id === playerId,
  );
}

export function firstEventCrossed(
  events: ReplayEvent[],
  previousTick: number,
  nextTick: number,
): ReplayEvent | undefined {
  return events.find(
    (event) => event.tick > previousTick && event.tick <= nextTick,
  );
}
