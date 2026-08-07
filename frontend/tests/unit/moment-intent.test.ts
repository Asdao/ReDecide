import { describe, expect, it } from "vitest";
import { momentIntentReducer } from "@/domain/moment-intent";

describe("moment intent state", () => {
  it("keeps the submitted intent while contextual analysis is generated and replaces coaching on success", () => {
    const generating = momentIntentReducer({}, {
      type: "SUBMIT",
      keyPointId: "event-1",
      intent: "I wanted to isolate the player on short.",
      requestId: 1,
    });

    expect(generating["event-1"]).toEqual({
      status: "generating",
      intent: "I wanted to isolate the player on short.",
      requestId: 1,
    });

    const complete = momentIntentReducer(generating, {
      type: "SUCCEED",
      keyPointId: "event-1",
      coaching: "Wait for the short player before committing.",
      requestId: 1,
    });

    expect(complete["event-1"]).toMatchObject({
      status: "complete",
      intent: "I wanted to isolate the player on short.",
      coaching: "Wait for the short player before committing.",
    });
  });

  it("stores intent independently for each analysis point", () => {
    const first = momentIntentReducer({}, {
      type: "SUBMIT",
      keyPointId: "event-1",
      intent: "First intent",
      requestId: 1,
    });
    const second = momentIntentReducer(first, {
      type: "SUBMIT",
      keyPointId: "event-2",
      intent: "Second intent",
      requestId: 2,
    });

    expect(second["event-1"].intent).toBe("First intent");
    expect(second["event-2"].intent).toBe("Second intent");
  });

  it("ignores a late response from an older request for the same point", () => {
    const first = momentIntentReducer({}, {
      type: "SUBMIT",
      keyPointId: "event-1",
      intent: "My intent",
      requestId: 1,
    });
    const retry = momentIntentReducer(first, {
      type: "SUBMIT",
      keyPointId: "event-1",
      intent: "My intent",
      requestId: 2,
    });

    expect(momentIntentReducer(retry, {
      type: "SUCCEED",
      keyPointId: "event-1",
      coaching: "Stale coaching",
      requestId: 1,
    })).toBe(retry);
  });

  it("keeps the original intent available for a same-text retry after failure", () => {
    const generating = momentIntentReducer({}, {
      type: "SUBMIT",
      keyPointId: "event-1",
      intent: "Hold the angle for my teammate.",
      requestId: 1,
    });
    const failed = momentIntentReducer(generating, {
      type: "FAIL",
      keyPointId: "event-1",
      message: "The new analysis could not be generated.",
      requestId: 1,
    });

    expect(failed["event-1"]).toMatchObject({
      status: "error",
      intent: "Hold the angle for my teammate.",
    });
  });
});
