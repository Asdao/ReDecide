import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import cardFixture from "@/fixtures/decision-card.json";
import packetFixture from "@/fixtures/decision-packet.json";
import {
  analyzeJsonRequestSchema,
  decisionBundleSchema,
  decisionCardSchema,
  decisionPacketSchema,
  intentInputSchema,
} from "@/domain/contracts";

describe("version 1.0 frontend contracts", () => {
  it("parses the checked-in packet, card, and intent", () => {
    expect(decisionPacketSchema.parse(packetFixture).schema_version).toBe("1.0");
    expect(decisionCardSchema.parse(cardFixture).verdict).toBe("REASONABLE_BUT_RISKY");
    expect(intentInputSchema.parse({ tag: " TAKE_DUEL ", text: "  reset first  " })).toEqual({
      tag: "TAKE_DUEL",
      text: "reset first",
    });
  });

  it("normalizes blank transport intent text to null", () => {
    const request = analyzeJsonRequestSchema.parse({
      decision_packet: packetFixture,
      intent: { tag: "TAKE_DUEL", text: "   " },
    });

    expect(request.intent.text).toBeNull();
  });

  it("rejects transport intent text longer than 240 characters", () => {
    expect(() =>
      analyzeJsonRequestSchema.parse({
        decision_packet: packetFixture,
        intent: { tag: "TAKE_DUEL", text: "x".repeat(241) },
      }),
    ).toThrow();
  });

  it("rejects extra fields", () => {
    expect(() => decisionCardSchema.parse({ ...cardFixture, outcome: "round won" })).toThrow();
  });

  it("rejects evidence after the decision boundary", () => {
    const firstEvidence = packetFixture.known_before_decision[0];
    const futurePacket = {
      ...packetFixture,
      known_before_decision: [
        { ...firstEvidence, tick: packetFixture.decision_open_tick + 1 },
      ],
    };

    expect(() => decisionPacketSchema.parse(futurePacket)).toThrow(
      "known_before_decision cannot contain future evidence",
    );
  });

  it("rejects mismatched packet and card IDs", () => {
    expect(() =>
      decisionBundleSchema.parse({
        packet: packetFixture,
        card: { ...cardFixture, decision_id: "another-decision" },
      }),
    ).toThrow("Decision packet and card decision_id values must match");
  });

  it("rejects card facts that are not present in the packet evidence", () => {
    expect(() =>
      decisionBundleSchema.parse({
        packet: packetFixture,
        card: { ...cardFixture, facts_used: [...cardFixture.facts_used, "E999"] },
      }),
    ).toThrow("unsupported evidence IDs");
  });
});

describe("local fixture compatibility", () => {
  it("matches the canonical backend fixtures", () => {
    const backendFixtures = path.resolve(process.cwd(), "..", "backend", "tests", "fixtures");
    const backendPacket: unknown = JSON.parse(
      readFileSync(path.join(backendFixtures, "decision_packet.valid.json"), "utf8"),
    );
    const backendCard: unknown = JSON.parse(
      readFileSync(path.join(backendFixtures, "decision_card.valid.json"), "utf8"),
    );

    expect(decisionPacketSchema.parse(packetFixture)).toEqual(
      decisionPacketSchema.parse(backendPacket),
    );
    expect(decisionCardSchema.parse(cardFixture)).toEqual(decisionCardSchema.parse(backendCard));
  });
});
