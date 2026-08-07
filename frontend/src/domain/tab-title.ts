import type { AnalysisFlowState } from "./analysis-flow";

const PRODUCT_NAME = "RE:DECIDE";

export type TabLocation = "Home" | "Samples" | "Replays" | "Replay" | "Analysis";
export type TabScreen = AnalysisFlowState["status"] | "processed-replays" | "processed-player";

export function formatTabTitle(location: TabLocation): string {
  return `${location} - ${PRODUCT_NAME}`;
}

export function tabLocationForScreen(screen: TabScreen): TabLocation {
  if (screen === "choose") return "Home";
  if (screen === "processed-replays") return "Replays";
  if (screen === "processed-player") return "Replay";
  if (screen.startsWith("sample") || screen === "loading-samples") return "Samples";
  if (
    screen === "running-coaching" ||
    screen === "recovering-result" ||
    screen === "loading-visualization" ||
    screen === "viewer"
  ) {
    return "Analysis";
  }
  return "Replay";
}
