import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildReplayFrames,
  firstEventCrossed,
  formatReplayTime,
  frameAtTick,
  playerTimelineEvents,
  roundAtTick,
  showcaseReplaySchema,
  worldToMirageRadar,
  type ShowcaseSnapshot,
} from "@/domain/replay-viewer";

const snapshot = (tick: number, playerId: string): ShowcaseSnapshot => ({
  tick,
  round_num: 1,
  player_id: playerId,
  display_name: playerId,
  side: playerId === "p1" ? "ct" : "t",
  X: 0,
  Y: 0,
  Z: 0,
  health: 100,
  armor: 0,
  alive: true,
  has_defuser: false,
  place: "Mid",
});

describe("processed replay viewer", () => {
  it("validates the bundled Mirage showcase", () => {
    const raw = readFileSync(
      resolve(process.cwd(), "public/replays/mirage-showcase.replay.json"),
      "utf8",
    );
    const replay = showcaseReplaySchema.parse(JSON.parse(raw));

    expect(replay.map).toEqual({ name: "de_mirage", tick_rate: 64 });
    expect(replay.players).toHaveLength(10);
    expect(replay.rounds).toHaveLength(30);
    expect(replay.ticks.length).toBeGreaterThan(60_000);
  });

  it("groups snapshots into frames and deterministically seeks to the previous frame", () => {
    const frames = buildReplayFrames([
      snapshot(128, "p2"),
      snapshot(64, "p1"),
      snapshot(128, "p1"),
    ]);

    expect(frames.map(({ tick }) => tick)).toEqual([64, 128]);
    expect(frames[1].snapshots.map(({ player_id }) => player_id)).toEqual(["p1", "p2"]);
    expect(frameAtTick(frames, 127)?.tick).toBe(64);
    expect(frameAtTick(frames, 128)?.tick).toBe(128);
    expect(frameAtTick(frames, 10)).toBeUndefined();
  });

  it("uses the reviewed Mirage overview transform", () => {
    expect(worldToMirageRadar(-3230, 1713)).toEqual({ left: 0, top: 0 });
    expect(worldToMirageRadar(1890, -3407)).toEqual({ left: 100, top: 100 });
  });

  it("finds rounds and formats the replay clock", () => {
    const rounds = [
      { round_num: 1, start: 100, end: 200, official_end: 220 },
      { round_num: 2, start: 220, end: 400 },
    ];

    expect(roundAtTick(rounds, 210)?.round_num).toBe(1);
    expect(roundAtTick(rounds, 220)?.round_num).toBe(2);
    expect(roundAtTick(rounds, 300)?.round_num).toBe(2);
    expect(formatReplayTime(3_940, 100, 64)).toBe("1:00");
  });

  it("shows only damage received and deaths for the selected player", () => {
    const events = [
      { event_id: "damage-in", event: "damage", tick: 100, round_num: 1, attacker_id: "p2", victim_id: "p1" },
      { event_id: "damage-out", event: "damage", tick: 110, round_num: 1, attacker_id: "p1", victim_id: "p2" },
      { event_id: "death", event: "kill", tick: 120, round_num: 1, attacker_id: "p2", victim_id: "p1" },
      { event_id: "plant", event: "plant", tick: 130, round_num: 1, player_id: "p1" },
    ];

    expect(playerTimelineEvents(events, "p1").map(({ event_id }) => event_id)).toEqual([
      "damage-in",
      "death",
    ]);

    const selectedEvents = playerTimelineEvents(events, "p1");
    expect(firstEventCrossed(selectedEvents, 90, 105)?.event_id).toBe("damage-in");
    expect(firstEventCrossed(selectedEvents, 100, 119)).toBeUndefined();
    expect(firstEventCrossed(selectedEvents, 100, 120)?.event_id).toBe("death");
  });
});
