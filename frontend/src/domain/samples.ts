import { z } from "zod";

export const sampleSummarySchema = z
  .object({
    sample_id: z.string().min(1),
    display_name: z.string().min(1),
    description: z.string().min(1),
    map: z.string().min(1),
    players: z.array(z.string().min(1)),
    recommended_player: z.string().min(1).nullable(),
    available: z.boolean(),
  })
  .strict();

export const samplesResponseSchema = z
  .object({
    samples: z.array(sampleSummarySchema),
  })
  .strict();

export const samplePreparationSchema = z
  .object({
    stage: z.enum(["PLAYER_SELECTION_REQUIRED", "INTENT_REQUIRED"]),
    analysis_id: z.string().min(1),
    players: z.array(z.string().min(1)),
    decision_packet: z.unknown().nullable(),
    neutral_summary: z.unknown().nullable(),
  })
  .strict();

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
