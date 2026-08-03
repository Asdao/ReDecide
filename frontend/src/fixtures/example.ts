import cardJson from "./decision-card.json";
import packetJson from "./decision-packet.json";
import { decisionBundleSchema } from "@/domain/contracts";

// Parse local recovery data at the same boundary used for network responses.
export const exampleDecision = decisionBundleSchema.parse({
  packet: packetJson,
  card: cardJson,
});
