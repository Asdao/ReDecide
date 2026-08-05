import type { Metadata } from "next";
import { ReplayAnalysisScreen } from "@/components/ReplayAnalysisScreen";

export const metadata: Metadata = {
  description: "Explore a processed CS2 replay on a synchronized 2D radar and timeline.",
};

export default async function AnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{ player?: string; replay?: string }>;
}) {
  const { player, replay } = await searchParams;
  return <ReplayAnalysisScreen initialPlayerId={player} replayId={replay} />;
}
