import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildReplayFrames,
  firstEventCrossed,
  formatReplayTime,
  frameAtTick,
  interpolatedSnapshotsAtTick,
  normalizeBackendReplay,
  playerTimelineEvents,
  radarOverviewForMap,
  roundAtTick,
  worldToRadar,
  type ReplaySnapshot,
} from "@/domain/replay-viewer";

const snapshot = (tick: number, playerId: string): ReplaySnapshot => ({
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
  it.each([
    ["mirage-showcase.replay.json", "de_mirage", 30, 60_000],
    ["inferno-processed.replay.json", "de_inferno", 29, 70_000],
  ])("normalizes the bundled backend replay %s", (filename, map, rounds, minimumTicks) => {
    const raw = readFileSync(resolve(process.cwd(), "public/replays", filename), "utf8");
    const replay = normalizeBackendReplay(JSON.parse(raw));

    expect(replay.map).toEqual({ name: map, tick_rate: 64 });
    expect(replay.players).toHaveLength(10);
    expect(replay.rounds).toHaveLength(rounds);
    expect(replay.ticks.length).toBeGreaterThan(minimumTicks);
    expect(replay.ticks.every(({ player_id, alive }) => player_id && typeof alive === "boolean")).toBe(true);
  });

  it("adapts backend snapshot names and derives optional alive state", () => {
    const replay = normalizeBackendReplay({
      schema_version: "replay_visualization_v1",
      replay_id: "backend-replay",
      source: "match.dem",
      map: { name: "de_inferno", tick_rate: 64 },
      players: [{ player_id: "stable-player", display_name: "Player One", sides: ["ct"] }],
      rounds: [{ round_num: 1, start: 1, end: 100 }],
      events: [{ event: "damage", tick: 20, round_num: 1, attacker_name: "Player One", victim_name: "Player One", dmg_health: 12 }],
      ticks: [{ tick: 10, round_num: 1, name: "Player One", player_name: "Player One", side: "ct", X: 1, Y: 2, Z: 3, health: 0, armor_value: 40 }],
    });

    expect(replay.ticks[0]).toMatchObject({
      player_id: "stable-player",
      display_name: "Player One",
      armor: 40,
      alive: false,
    });
    expect(replay.events[0]).toMatchObject({
      attacker_id: "stable-player",
      victim_id: "stable-player",
      damage_health: 12,
    });
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

  it("interpolates player movement between adjacent snapshots", () => {
    const start = { ...snapshot(64, "p1"), X: 0, Y: 20, Z: -10 };
    const end = { ...snapshot(128, "p1"), X: 100, Y: 60, Z: 10 };
    const frames = buildReplayFrames([start, end]);

    expect(interpolatedSnapshotsAtTick(frames, 96)[0]).toMatchObject({
      X: 50,
      Y: 40,
      Z: 0,
    });
  });

  it("uses reviewed map-specific overview transforms", () => {
    const mirage = radarOverviewForMap("de_mirage");
    const inferno = radarOverviewForMap("de_inferno");
    expect(mirage).toBeDefined();
    expect(inferno).toBeDefined();
    expect(worldToRadar(-3230, 1713, mirage!)).toEqual({ left: 0, top: 0 });
    expect(worldToRadar(2930.6, -1147.6, inferno!)).toEqual({ left: 100, top: 100 });
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
