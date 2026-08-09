# RE:DECIDE energetic submission voiceover

Target: **4:20–4:30** over `redecide-demo-draft.mp4`.

Delivery: confident, urgent and conversational. Start fast, pause briefly on the
product promise, then build energy again. The text in **bold** is emphasis—not
additional narration.

## Video sync cues

The MP4 is exactly **4:35**. Begin each section when the matching title appears:

| Video time | Visual on screen | Voiceover section |
|---|---|---|
| 0:00 | RE:DECIDE title and Mirage radar | The decision that changes the round |
| 0:20 | Two ways into the review | Start with the player's real match |
| 0:45 | Telemetry, not video | Turn a full replay into relevant moments |
| 1:10 | A bounded coaching pipeline | Facts, estimates, and coaching stay separate |
| 1:30 | The whole match remains navigable | Make the whole match understandable |
| 2:00 | Markers are not verdicts | Find the moments that matter |
| 2:25 | Jump straight to the moment | Coach the decision, not the final outcome |
| 2:50 | Add what telemetry cannot know | Add what telemetry can never know |
| 3:15 | Judge only what was knowable | Reliability is part of the product |
| 3:40 | Working vertical slice | A real working vertical slice |
| 4:00 | Prototype boundaries | What comes next |
| 4:15 | Final RE:DECIDE promise | Close |
| 4:27–4:35 | Final frame remains visible | No narration; allow the ending to breathe |

## 0:00–0:20 — The decision that changes the round

You take first damage. In two seconds, do you fight, fall back, use utility, or
wait for support? That choice can change the round—but finding it inside an
hour-long replay is slow and easy to judge with hindsight. **RE:DECIDE fixes
that. Don't replay the match. Replay the decision.**

## 0:20–0:45 — Start with the player's real match

Players do not need to record, edit, or upload video. They can open a prepared
example or submit the native CS2 demo they already have. RE:DECIDE sends that
demo to FastAPI and parses it once into structured telemetry: rounds, players,
positions, damage, deaths, and the events that shape each fight. We analyse the
game data—not millions of video pixels.

## 0:45–1:10 — Turn a full replay into relevant moments

The match roster comes straight from the parser, so the player chooses exactly
whose perspective to review. From there, RE:DECIDE searches the match for that
player's first-damage contacts: the moments where a safe reset can turn into a
risky re-engagement. Instead of dumping an entire match on the player, we
surface a focused set of decision points spread across the replay.

## 1:10–1:30 — Facts, estimates, and coaching stay separate

This separation is critical. The replay engine establishes the facts. The
value model estimates the round state. The coach converts bounded evidence into
an actionable adjustment. The language model does not parse the demo, rewrite
the telemetry, or decide which replay facts are true. **Facts first. Coaching
second.**

## 1:30–2:00 — Make the whole match understandable

Now the replay becomes interactive. The radar reconstructs every player's
movement, while the full timeline lets us jump between rounds and events. The
selected player stays visible, teammates and opponents remain distinct, and
damage, death, and analysis markers show where attention is needed. The
win-chance strip adds context about the round state—but never pretends that a
probability alone proves a decision was good or bad.

## 2:00–2:25 — Find the moments that matter

This is the difference between watching and learning. A normal replay tells us
what happened. RE:DECIDE takes us directly to the instant the decision opened.
We can inspect the contact, understand the immediate reaction, and connect the
moment to a practical coaching adjustment. No scrubbing through fifty minutes.
No generic post-match summary. **One moment. One choice. A better response next
time.**

## 2:25–2:50 — Coach the decision, not the final outcome

At an analysed marker, the coaching panel focuses on the immediate choice:
reset behind cover, reposition, create space with utility, wait for support, or
re-engage. The recommendation stays attached to the exact player and exact
decision. That makes the feedback specific enough to practise—instead of being
another vague instruction to “aim better” or “play safer.”

## 2:50–3:15 — Add what telemetry can never know

But replay data has one blind spot: it cannot know the player's intention. So
we ask. “I wanted to get information and fall back.” That single sentence adds
the missing human context. RE:DECIDE interprets the tactical goal, resolves the
exact selected moment, and returns contextual coaching without treating the
player's explanation as a confirmed replay fact.

## 3:15–3:40 — Reliability is part of the product

This is where RE:DECIDE differs from a generic chatbot. The coach receives only
the contact state and bounded immediate reaction. It cannot use a later death,
the round winner, or the final match result to pretend the earlier choice was
obvious. Unsupported evidence is rejected. Unknown information stays unknown.
If the provider cannot produce a grounded answer, the backend fails safely.

## 3:40–4:00 — A real working vertical slice

The system is connected end to end: a Next.js replay experience, FastAPI and
Pydantic validation, Awpy parsing, LightGBM estimates, and bounded
language-model coaching. Local demo upload works today; hosted Blob transport
is next. Each layer has one clear job, making the product testable and ready to
improve.

## 4:00–4:15 — What comes next

This is a working prototype—not a claim of perfect tactical truth. Next, we
validate advice with CS2 experts, test more unseen matches, and add scored
alternatives with calibrated abstention. We prove the coaching before scaling
the platform.

## 4:15–4:27 — Close

RE:DECIDE transforms raw match telemetry into a decision the player can learn
from. Faster review. Specific coaching. Accountable evidence. **Don't replay
the match. Replay the decision.**

## Optional eight-second final hold

Stop speaking and let the closing frame remain visible. Add the team name,
challenge name, and quiet music fade in the editor if required.

## Emergency cuts if the read exceeds 4:30

Remove these sentences in order:

1. “We analyse the game data—not millions of video pixels.”
2. “The selected player stays visible, teammates and opponents remain distinct.”
3. “That makes the feedback specific enough to practise—instead of being another vague instruction to ‘aim better’ or ‘play safer.’”
4. “Each layer has one clear job, which makes the product testable, replaceable, and ready to improve.”
