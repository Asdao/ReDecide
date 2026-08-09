export type MomentIntentRequest = {
  replayId: string;
  analysisId: string;
  playerId: string;
  keyPointId: string;
  decisionId: string;
  intent: string;
};

export type MomentIntentSubmission = (
  request: MomentIntentRequest,
  signal: AbortSignal,
) => Promise<string>;

export type MomentIntentState =
  | {
      status: "generating";
      intent: string;
      requestId: number;
      coaching?: string;
    }
  | {
      status: "complete";
      intent: string;
      requestId: number;
      coaching: string;
    }
  | {
      status: "error";
      intent: string;
      requestId: number;
      message: string;
      coaching?: string;
    };

export type MomentIntentStates = Readonly<Record<string, MomentIntentState>>;

export type MomentIntentAction =
  | {
      type: "SUBMIT";
      keyPointId: string;
      intent: string;
      requestId: number;
    }
  | {
      type: "SUCCEED";
      keyPointId: string;
      coaching: string;
      requestId: number;
    }
  | {
      type: "FAIL";
      keyPointId: string;
      message: string;
      requestId: number;
    };

export function momentIntentReducer(
  state: MomentIntentStates,
  action: MomentIntentAction,
): MomentIntentStates {
  if (action.type === "SUBMIT") {
    const previous = state[action.keyPointId];
    const previousCoaching = previous && "coaching" in previous
      ? previous.coaching
      : undefined;
    return {
      ...state,
      [action.keyPointId]: {
        status: "generating",
        intent: action.intent,
        requestId: action.requestId,
        ...(previousCoaching ? { coaching: previousCoaching } : {}),
      },
    };
  }

  const current = state[action.keyPointId];
  if (!current || current.requestId !== action.requestId) {
    return state;
  }

  if (action.type === "SUCCEED") {
    return {
      ...state,
      [action.keyPointId]: {
        status: "complete",
        intent: current.intent,
        requestId: current.requestId,
        coaching: action.coaching,
      },
    };
  }

  return {
    ...state,
    [action.keyPointId]: {
      status: "error",
      intent: current.intent,
      requestId: current.requestId,
      message: action.message,
      ...(current.coaching ? { coaching: current.coaching } : {}),
    },
  };
}
