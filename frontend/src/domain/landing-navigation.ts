export type LandingView = "home" | "samples" | "showcase";
export type LandingHistoryView = LandingView | "upload";

type LandingHistoryMarker = {
  view: LandingHistoryView;
  child: boolean;
};

const historyMarkerKey = "redecideLanding";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function landingViewFromSearch(search: string): LandingView {
  const view = new URLSearchParams(search).get("view");
  return view === "samples" || view === "showcase" ? view : "home";
}

export function landingViewHref(view: LandingView, currentSearch = ""): string {
  const params = new URLSearchParams(currentSearch);
  if (view === "home") {
    params.delete("view");
  } else {
    params.set("view", view);
  }

  const query = params.toString();
  return query ? `/?${query}` : "/";
}

export function withLandingHistoryMarker(
  state: unknown,
  view: LandingHistoryView,
  child: boolean,
): Record<string, unknown> {
  return {
    ...(isRecord(state) ? state : {}),
    [historyMarkerKey]: { view, child } satisfies LandingHistoryMarker,
  };
}

export function isLandingChildHistoryEntry(
  state: unknown,
  view?: Exclude<LandingHistoryView, "home">,
): boolean {
  if (!isRecord(state)) {
    return false;
  }

  const marker = state[historyMarkerKey];
  if (!isRecord(marker) || marker.child !== true) {
    return false;
  }

  return view === undefined
    ? marker.view === "samples" || marker.view === "showcase" || marker.view === "upload"
    : marker.view === view;
}
