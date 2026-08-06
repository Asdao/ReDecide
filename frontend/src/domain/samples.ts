import { z } from "zod";
import { decisionPacketSchema } from "@/domain/contracts";

const requiredString = z.string().trim().min(1);

export const sampleSummarySchema = z
  .object({
    sample_id: requiredString,
    display_name: requiredString,
    description: requiredString,
    map: requiredString,
    players: z.array(requiredString),
    recommended_player: requiredString.nullable(),
    available: z.boolean(),
  })
  .strict()
  .superRefine((sample, context) => {
    if (new Set(sample.players).size !== sample.players.length) {
      context.addIssue({
        code: "custom",
        message: "sample players must be unique",
        path: ["players"],
      });
    }
    if (
      sample.recommended_player !== null &&
      !sample.players.includes(sample.recommended_player)
    ) {
      context.addIssue({
        code: "custom",
        message: "recommended_player must appear in players",
        path: ["recommended_player"],
      });
    }
  });

export const samplesResponseSchema = z
  .object({
    samples: z.array(sampleSummarySchema),
  })
  .strict();

const samplePreparationBase = {
  analysis_id: requiredString,
  players: z.array(requiredString),
};

const neutralDecisionSummarySchema = z
  .object({
    timestamp_seconds: z.number().nonnegative(),
    text: requiredString,
  })
  .strict();

export const samplePreparationSchema = z.discriminatedUnion("stage", [
  z
    .object({
      ...samplePreparationBase,
      stage: z.literal("PLAYER_SELECTION_REQUIRED"),
      decision_packet: z.null(),
      neutral_summary: z.null(),
    })
    .strict(),
  z
    .object({
      ...samplePreparationBase,
      stage: z.literal("INTENT_REQUIRED"),
      decision_packet: decisionPacketSchema,
      neutral_summary: neutralDecisionSummarySchema,
    })
    .strict(),
]);

export type SampleSummary = z.infer<typeof sampleSummarySchema>;
export type SamplePreparation = z.infer<typeof samplePreparationSchema>;

const hostagesMaps = new Set(["agency", "italy", "office"]);
const armsRaceMaps = new Set(["baggage", "pool_day", "shoots"]);
const bundledMapThumbnails = new Set(["de_mirage"]);

export function mapAssetKey(map: string): string {
  const slug = map
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");

  if (/^(?:ar|cs|de)_/.test(slug)) {
    return slug;
  }
  if (hostagesMaps.has(slug)) {
    return `cs_${slug}`;
  }
  if (armsRaceMaps.has(slug)) {
    return `ar_${slug}`;
  }
  return `de_${slug}`;
}

export function mapThumbnailUrl(map: string): string {
  const assetKey = mapAssetKey(map);
  if (bundledMapThumbnails.has(assetKey)) {
    return `/maps/${assetKey}.png`;
  }
  return `https://raw.githubusercontent.com/MurkyYT/cs2-map-icons/main/images/thumbs/${assetKey}_png.png`;
}
