import { z } from "zod";

const requiredString = z.string().trim().min(1);
const contractVersion = z.string().trim().regex(/^1\.0$/);
const evidenceId = z.string().trim().min(1);

export const decisionTypeSchema = z
  .string()
  .trim()
  .pipe(z.enum(["POST_CONTACT_RESET"]));

export const observedActionLabelSchema = z
  .string()
  .trim()
  .pipe(
    z.enum([
      "IMMEDIATE_REENGAGE",
      "RESET_REPOSITION",
      "RELOAD_EXPOSED",
      "HOLD_FOR_SUPPORT",
      "UNCLASSIFIED",
    ]),
  );

export const intentTagSchema = z
  .string()
  .trim()
  .pipe(
    z.enum(["TAKE_DUEL", "CREATE_SPACE", "HELP_TEAMMATE", "ESCAPE", "UNKNOWN"]),
  );

export const verdictSchema = z
  .string()
  .trim()
  .pipe(
    z.enum([
      "GOOD_DECISION",
      "REASONABLE_BUT_RISKY",
      "POOR_DECISION",
      "INSUFFICIENT_EVIDENCE",
    ]),
  );

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

export const evidenceItemSchema = z
  .object({
    evidence_id: evidenceId,
    tick: z.number().int().nonnegative(),
    category: requiredString,
    statement: requiredString,
    value: jsonValueSchema,
    source: requiredString,
  })
  .strict();

const observedActionSchema = z
  .object({
    label: observedActionLabelSchema,
    description: requiredString,
    evidence_ids: z.array(evidenceId),
  })
  .strict()
  .refine(({ evidence_ids }) => new Set(evidence_ids).size === evidence_ids.length, {
    message: "observed_action evidence_ids must be unique",
    path: ["evidence_ids"],
  });

const dataQualitySchema = z
  .object({
    score: z.number().min(0).max(1),
    warnings: z.array(z.string().trim()),
  })
  .strict();

export const decisionPacketSchema = z
  .object({
    schema_version: contractVersion,
    decision_id: requiredString,
    match_id: requiredString,
    map: requiredString,
    round_number: z.number().int().min(1),
    player: requiredString,
    decision_type: decisionTypeSchema,
    decision_open_tick: z.number().int().nonnegative(),
    decision_open_seconds: z.number().nonnegative(),
    action_close_tick: z.number().int().nonnegative(),
    known_before_decision: z.array(evidenceItemSchema),
    observed_action: observedActionSchema,
    unknowns: z.array(z.string().trim()),
    data_quality: dataQualitySchema,
  })
  .strict()
  .superRefine((packet, context) => {
    if (packet.action_close_tick < packet.decision_open_tick) {
      context.addIssue({
        code: "custom",
        message: "action_close_tick must be at or after decision_open_tick",
        path: ["action_close_tick"],
      });
    }

    const knownIds = new Set<string>();
    packet.known_before_decision.forEach((item, index) => {
      if (item.tick > packet.decision_open_tick) {
        context.addIssue({
          code: "custom",
          message: "known_before_decision cannot contain future evidence",
          path: ["known_before_decision", index, "tick"],
        });
      }
      if (knownIds.has(item.evidence_id)) {
        context.addIssue({
          code: "custom",
          message: "known_before_decision evidence_ids must be unique",
          path: ["known_before_decision", index, "evidence_id"],
        });
      }
      knownIds.add(item.evidence_id);
    });
  });

export const intentInputSchema = z
  .object({
    tag: intentTagSchema,
    text: z.string().trim().nullable().optional(),
  })
  .strict();

const decisionOptionSchema = z
  .object({
    action: requiredString,
    tradeoff: requiredString,
    when_best: requiredString,
  })
  .strict();

const nextMatchQuestSchema = z
  .object({
    cue: requiredString,
    action: requiredString,
    success_check: requiredString,
  })
  .strict();

const decisionChecksSchema = z
  .object({
    unsupported_evidence_ids: z.array(z.string().trim()),
    future_information_detected: z.boolean(),
    contradiction_detected: z.boolean(),
  })
  .strict();

export const decisionCardSchema = z
  .object({
    schema_version: contractVersion,
    decision_id: requiredString,
    title: requiredString,
    verdict: verdictSchema,
    confidence: z.number().min(0).max(1),
    assessment: requiredString,
    player_intent_summary: requiredString,
    facts_used: z.array(evidenceId),
    options: z.array(decisionOptionSchema),
    recommended_action: requiredString,
    why: requiredString,
    execution_note: z.string().trim().nullable().optional(),
    next_match_quest: nextMatchQuestSchema,
    limitations: z.array(z.string().trim()),
    checks: decisionChecksSchema,
  })
  .strict()
  .refine(({ facts_used }) => new Set(facts_used).size === facts_used.length, {
    message: "facts_used evidence IDs must be unique",
    path: ["facts_used"],
  });

export const analyzeJsonRequestSchema = z
  .object({
    decision_packet: decisionPacketSchema,
    intent: intentInputSchema,
  })
  .strict()
  .superRefine(({ intent }, context) => {
    // The backend applies this transport-only limit after stripping text.
    if (
      intent.text !== null &&
      intent.text !== undefined &&
      Array.from(intent.text).length > 240
    ) {
      context.addIssue({
        code: "custom",
        message: "intent text cannot exceed 240 characters",
        path: ["intent", "text"],
      });
    }
  })
  // AnalyzeJsonRequest normalizes a blank (or whitespace-only) intent to null
  // after the nested IntentInput has been stripped, matching the backend
  // transport contract.
  .transform(({ decision_packet, intent }) => ({
    decision_packet,
    intent: {
      ...intent,
      text: intent.text === "" ? null : intent.text,
    },
  }));

export const decisionBundleSchema = z
  .object({
    packet: decisionPacketSchema,
    card: decisionCardSchema,
  })
  .strict()
  .superRefine(({ packet, card }, context) => {
    if (packet.decision_id !== card.decision_id) {
      context.addIssue({
        code: "custom",
        message: "Decision packet and card decision_id values must match",
        path: ["card", "decision_id"],
      });
    }

    const availableEvidenceIds = new Set([
      ...packet.known_before_decision.map(({ evidence_id }) => evidence_id),
      ...packet.observed_action.evidence_ids,
    ]);
    const unsupportedEvidenceIds = card.facts_used.filter(
      (evidenceId) => !availableEvidenceIds.has(evidenceId),
    );
    if (unsupportedEvidenceIds.length > 0) {
      context.addIssue({
        code: "custom",
        message: `DecisionCard contains unsupported evidence IDs: ${unsupportedEvidenceIds.join(", ")}`,
        path: ["card", "facts_used"],
      });
    }
  });

export type DecisionPacket = z.infer<typeof decisionPacketSchema>;
export type IntentInput = z.infer<typeof intentInputSchema>;
export type AnalyzeJsonRequest = z.infer<typeof analyzeJsonRequestSchema>;
export type DecisionCard = z.infer<typeof decisionCardSchema>;
export type DecisionBundle = z.infer<typeof decisionBundleSchema>;
