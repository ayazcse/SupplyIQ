# AI Safety / Hallucination Control

## The core guarantee

The AI Supply Chain Analyst (`src/llm/ai_analyst.py`) is a **retrieve-then-
generate** system, not a chatbot with general knowledge of "the business."
There is no business for it to have general knowledge of — the only facts
it can reference are the ones retrieved into `context["data"]` by
`retrieve_context()` before any answer is produced, whether that answer
comes from the local template or a real LLM call.

## How grounding is enforced

1. **Retrieval happens first, unconditionally.** `retrieve_context()` runs
   keyword matching against the question, pulls the relevant precomputed
   JSON/SQL results (supplier risk, SKU risk, inventory, recommendations,
   business impact), and returns a structured `context` dict — *before*
   either answer path (local or LLM) is invoked.
2. **The LLM system prompt explicitly forbids answering outside the
   context**: *"You must answer ONLY using the structured JSON context
   provided below — never invent numbers, supplier names, or SKUs that are
   not present in the context. If the context does not contain enough
   information to answer, say 'Insufficient evidence to determine the root
   cause' (or similar) rather than guessing."* (see `SYSTEM_PROMPT` in
   `src/llm/ai_analyst.py`).
3. **The local fallback mode enforces the same contract mechanically**: if
   no matching data was retrieved, `local_fallback_answer()` returns a
   fixed "Insufficient evidence" response rather than attempting to
   construct an answer from nothing. There is no code path in local mode
   that can fabricate a number — every figure in the template is an
   f-string interpolation of a real value from `context["data"]`.
4. **Response contract is fixed** for both modes: INSIGHT / EVIDENCE /
   BUSINESS IMPACT / RECOMMENDATION / CONFIDENCE & LIMITATION. This keeps
   the LLM-backed and local-fallback answers structurally comparable, and
   forces every answer to explicitly state its own confidence/limitations
   rather than presenting a number with false certainty.

## What this does NOT protect against

Being honest about the limits of this design, since overclaiming safety
guarantees would itself be a form of the problem this section is about:

- If an LLM is used and it ignores the system prompt (a known LLM failure
  mode), nothing in this codebase can force compliance after the fact — no
  output-side fact-checking against the context is implemented. A
  production version of this would add a post-hoc verifier step (e.g.,
  regex/parse the LLM's numeric claims and check them against `context`).
- The keyword-based intent matching in `retrieve_context()` is simple and
  can miss a question's actual intent for unusually phrased queries,
  returning the generic `general_snapshot` context instead of the most
  relevant one. This is a retrieval-quality limitation, not a hallucination
  risk (the answer will still be grounded in *some* real data), but it
  could produce an answer that doesn't actually address what was asked.
- Business impact figures are clearly labeled "estimated/simulated"
  throughout (in the JSON itself and in every surface that displays them),
  but a careless reader could still mistake them for real financial results
  if they only see the app's UI without the disclaimer text — the
  disclaimer is included in the app and API payloads specifically to guard
  against this.

## Testing performed

`src/llm/ai_analyst.py` was run directly (`python -m src.llm.ai_analyst`)
against 5 representative questions in **local fallback mode** (no API key
configured in the build environment), and via `POST /ask` through the live
FastAPI server, and confirmed to: (a) retrieve real data matching the
question's intent, (b) never emit a name/number absent from that retrieved
data, and (c) explicitly state "Insufficient evidence" when a synthetic
"no data available" scenario was tested. The LLM-backed code path
(Anthropic/OpenAI) was implemented per each provider's public API
specification but **was not exercised against a live API key** during this
build — verify it yourself by setting `LLM_PROVIDER`/`LLM_API_KEY` in `.env`.
