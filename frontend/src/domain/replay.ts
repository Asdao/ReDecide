import { z } from "zod";

const requiredString = z.string().trim().min(1);
const nonnegativeInteger = z.number().int().nonnegative();

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(jsonValueSchema),
    z.record(z.string(), jsonValueSchema),
  ]),
);

const replayMapSchema = z
  .object({
    name: requiredString,
    tick_rate: z.number().positive(),
  })
  .strict();

const replayPlayerSchema = z
  .object({
    player_id: requiredString,
    display_name: requiredString.nullable(),
    sides: z.array(requiredString),
  })
  .strict();

const replayRoundBoundarySchema = z
  .object({
    round_num: nonnegativeInteger.nullable(),
    start: nonnegativeInteger.nullable(),
    end: nonnegativeInteger.nullable(),
  })
  .strict();

export const replayManifestSchema = z
  .object({
    schema_version: z.literal("replay_manifest_v1"),
    replay_id: requiredString,
    source: requiredString,
    map: replayMapSchema,
    players: z.array(replayPlayerSchema),
    rounds: z.array(replayRoundBoundarySchema),
    visualization_status: z.enum(["processing", "ready", "failed"]),
    coaching_status: z.enum(["ready", "complete"]),
    visualization_unlocked: z.boolean(),
    visualization_error: requiredString.optional(),
  })
  .strict()
  .superRefine((manifest, context) => {
    const playerIds = manifest.players.map(({ player_id }) => player_id);
    if (new Set(playerIds).size !== playerIds.length) {
      context.addIssue({
        code: "custom",
        message: "replay manifest player_id values must be unique",
        path: ["players"],
      });
    }

    manifest.rounds.forEach((round, index) => {
      if (round.start !== null && round.end !== null && round.end < round.start) {
        context.addIssue({
          code: "custom",
          message: "replay round end must be at or after its start",
          path: ["rounds", index, "end"],
        });
      }
    });
  });

export const analysisJobSchema = z
  .object({
    analysis_id: requiredString,
    status: z.enum(["processing", "ready", "complete", "failed"]),
    players_available: z.boolean(),
    result_available: z.boolean(),
    logs_url: requiredString,
    events_url: requiredString,
    result_url: requiredString,
  })
  .strict();

export const analysisPlayerSchema = z
  .object({
    player_id: requiredString,
    display_name: requiredString.nullable(),
    side_by_round: z.record(z.string(), z.enum(["ct", "t"])),
    rounds: z.array(nonnegativeInteger),
    event_ids: z.array(requiredString),
    key_event_ids: z.array(requiredString),
    decision_ids: z.array(requiredString),
  })
  .strict();

export const analysisPlayersSchema = z
  .object({
    analysis_id: requiredString,
    status: z.enum(["processing", "ready", "complete", "failed"]),
    players: z.array(analysisPlayerSchema),
  })
  .strict()
  .superRefine(({ players }, context) => {
    const playerIds = players.map(({ player_id }) => player_id);
    if (new Set(playerIds).size !== playerIds.length) {
      context.addIssue({
        code: "custom",
        message: "analysis player_id values must be unique",
        path: ["players"],
      });
    }
  });

const analysisEventSchema = z
  .object({
    event_id: requiredString,
    event_type: requiredString,
    is_coaching_anchor: z.boolean(),
    is_key_event: z.boolean(),
    key_event_type: requiredString.nullable(),
    participant_ids: z.array(requiredString),
    round_number: z.number().int(),
    tick: nonnegativeInteger,
  })
  .strict();

const analysisCandidateSchema = z
  .object({
    action_close_tick: nonnegativeInteger,
    contact_tick: nonnegativeInteger,
    decision_id: requiredString,
    decision_open_tick: nonnegativeInteger,
    display_name: requiredString.nullable(),
    event_category: requiredString,
    evidence: z.array(requiredString),
    observed_action: requiredString,
    observed_action_confidence: z.number().min(0).max(1),
    opponent_id: requiredString,
    player_id: requiredString,
    player_name: requiredString.optional(),
    role: requiredString,
    round_number: z.number().int(),
    side: requiredString,
  })
  .strict();

const winTimelinePointSchema = z
  .object({
    ct_probability: z.number().min(0).max(1),
    round_number: z.number().int(),
    t_probability: z.number().min(0).max(1),
    tick: nonnegativeInteger,
    uncertainty: z.number().min(0).max(1),
  })
  .strict();

export const replayAnalysisResultSchema = z
  .object({
    schema_version: z.literal("replay_pipeline_v1"),
    report_type: z.literal("replay_pipeline_analysis"),
    source: requiredString,
    replay_id: requiredString,
    map_name: requiredString,
    players: z.array(analysisPlayerSchema),
    events: z.array(analysisEventSchema),
    key_events: z.array(analysisEventSchema),
    filter_contract: z
      .object({
        player_event_field: requiredString,
        player_reference_fields: z.array(requiredString),
        global_unfiltered_fields: z.array(requiredString),
      })
      .strict(),
    decision_candidates: z.array(analysisCandidateSchema),
    selected_decision: analysisCandidateSchema,
    coach_analysis: z
      .object({
        decision_id: requiredString,
        player_id: requiredString,
        player_name: requiredString,
        source: z.literal("pi"),
        what_could_be_done_better: requiredString,
      })
      .passthrough(),
    win_estimator: z
      .object({
        filtered_by_player: z.literal(false),
        model_available: z.boolean(),
        model_type: requiredString,
        scope: z.literal("global_team_probability"),
        timeline: z.array(winTimelinePointSchema),
        warning: requiredString.optional(),
      })
      .strict(),
    summary: z
      .object({
        player_count: nonnegativeInteger,
        event_count: nonnegativeInteger,
        key_event_count: nonnegativeInteger,
        decision_candidate_count: nonnegativeInteger,
        anchor: requiredString,
        anchor_fallback: z.boolean(),
        analysis_available: z.boolean(),
        outcome_blind: z.literal(true),
      })
      .strict(),
    replay_outcome: z
      .object({
        eventual_winner: z.enum(["CT", "T"]).nullable(),
        round_score: z
          .object({
            CT: nonnegativeInteger,
            T: nonnegativeInteger,
          })
          .strict(),
        source: z.enum(["declared_match_winner", "round_score"]),
      })
      .strict(),
  })
  .strict()
  .superRefine((result, context) => {
    const playerIds = result.players.map(({ player_id }) => player_id);
    if (new Set(playerIds).size !== playerIds.length) {
      context.addIssue({
        code: "custom",
        message: "analysis result player_id values must be unique",
        path: ["players"],
      });
    }

    const candidate = result.decision_candidates.find(
      ({ decision_id }) => decision_id === result.selected_decision.decision_id,
    );
    if (!candidate || candidate.player_id !== result.selected_decision.player_id) {
      context.addIssue({
        code: "custom",
        message: "selected decision must match a returned decision candidate",
        path: ["selected_decision", "decision_id"],
      });
    }

    if (
      result.coach_analysis.decision_id !== result.selected_decision.decision_id ||
      result.coach_analysis.player_id !== result.selected_decision.player_id
    ) {
      context.addIssue({
        code: "custom",
        message: "coaching analysis must match the selected decision and player",
        path: ["coach_analysis"],
      });
    }

    if (!playerIds.includes(result.selected_decision.player_id)) {
      context.addIssue({
        code: "custom",
        message: "selected player must appear in the analysis player list",
        path: ["selected_decision", "player_id"],
      });
    }
  });

const replayVisualizationPlayerSchema = replayPlayerSchema;

export const replayVisualizationSchema = z
  .object({
    schema_version: z.literal("replay_visualization_v1"),
    replay_id: requiredString,
    source: requiredString,
    map: replayMapSchema,
    players: z.array(replayVisualizationPlayerSchema),
    rounds: z.array(z.record(z.string(), jsonValueSchema)),
    events: z.array(z.record(z.string(), jsonValueSchema)),
    ticks: z.array(z.record(z.string(), jsonValueSchema)),
  })
  .strict()
  .superRefine(({ players }, context) => {
    const playerIds = players.map(({ player_id }) => player_id);
    if (new Set(playerIds).size !== playerIds.length) {
      context.addIssue({
        code: "custom",
        message: "visualization player_id values must be unique",
        path: ["players"],
      });
    }
  });

export type ReplayManifest = z.infer<typeof replayManifestSchema>;
export type AnalysisJob = z.infer<typeof analysisJobSchema>;
export type AnalysisPlayer = z.infer<typeof analysisPlayerSchema>;
export type AnalysisPlayers = z.infer<typeof analysisPlayersSchema>;
export type ReplayAnalysisResult = z.infer<typeof replayAnalysisResultSchema>;
export type ReplayVisualization = z.infer<typeof replayVisualizationSchema>;
