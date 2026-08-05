import type { Metadata } from "next";
import { ReplayAnalysisScreen } from "@/components/ReplayAnalysisScreen";

export const metadata: Metadata = {
  title: "Mirage replay analysis · RE:DECIDE",
  description: "Explore a processed CS2 Mirage replay on a synchronized 2D radar and timeline.",
};

export default async function AnalysisPage({
  searchParams,
}: {
  searchParams: Promise<{ player?: string }>;
}) {
  const { player } = await searchParams;
  return <ReplayAnalysisScreen initialPlayerId={player} />;
}
