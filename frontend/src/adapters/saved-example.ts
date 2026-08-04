import packetJson from "@/fixtures/decision-packet.json";
import { decisionPacketSchema, type DecisionPacket } from "@/domain/contracts";

const savedPacket: unknown = packetJson;

export function loadSavedExample(): DecisionPacket {
  return decisionPacketSchema.parse(savedPacket);
}
