# Migration Plan: Groq → IBM watsonx.ai

This document is a **planning-only** guide (no code changes yet) for replacing Groq Cloud
with IBM watsonx.ai as the LLM provider in this project. Follow the phases in order;
each phase lists the files that will eventually be touched so the change can be scoped
and reviewed incrementally.

---

## 0. Current Groq Footprint (for reference)

| Concern | File(s) |
|---|---|
| SDK wrapper (`chat_complete`, `chat_complete_json`, JSON extraction, retries) | [llm/groq_client.py](llm/groq_client.py) |
| Multi-key round-robin manager | [llm/key_manager.py](llm/key_manager.py) |
| Config / env vars (`GROQ_API_KEY`, `GROQ_MODEL`, etc.) | [config.py](config.py) |
| Direct `GroqClient` / `JSONParseError` imports | [core/content_analyzer.py](core/content_analyzer.py), [core/presentation_planner.py](core/presentation_planner.py), [core/presentation_planner_v3.py](core/presentation_planner_v3.py), [core/presentation_planner_template1.py](core/presentation_planner_template1.py), [core/slide_generator.py](core/slide_generator.py), [core/chunk_analyzer.py](core/chunk_analyzer.py), [core/consolidator.py](core/consolidator.py), [core/document_structure.py](core/document_structure.py), [core/dynamic_chunker.py](core/dynamic_chunker.py) |
| UI: key entry, model picker, branding, error handling | [app.py](app.py) |
| Dependency | [requirements.txt](requirements.txt) (`groq>=0.9.0`) |

Everything downstream of the LLM client only depends on two methods —
`chat_complete(messages, temperature, max_tokens) -> str` and
`chat_complete_json(messages, temperature, max_tokens) -> dict`. That narrow interface is
what makes a drop-in replacement feasible.

---

## Phase 1 — IBM Cloud & watsonx.ai Account Setup

1. Create/sign in to an **IBM Cloud** account (cloud.ibm.com).
2. Provision a **watsonx.ai (Studio) service instance** in a supported region
   (e.g. `us-south`, `eu-de`, `eu-gb`, `jp-tok`).
3. Create a **watsonx.ai Project** (Studio → Projects → New project) — this gives you a
   **Project ID** (GUID), needed for every inference call.
   - Alternative: use a **Deployment Space** + **Deployment ID** if you plan to deploy a
     tuned/served model endpoint instead of calling a foundation model directly.
4. Create an **IBM Cloud API key** (Manage → Access (IAM) → API keys → Create).
   This key is exchanged at runtime for a short-lived IAM bearer token by the SDK.
5. Note the **service URL** for your region, e.g.
   `https://us-south.ml.cloud.ibm.com`.
6. Decide which **foundation model(s)** to use (Prompt Lab → view available models), e.g.
   - `ibm/granite-3-8b-instruct` (IBM's own, cheapest/fastest)
   - `meta-llama/llama-3-3-70b-instruct`
   - `mistralai/mixtral-8x7b-instruct-v01`
   Check that the model supports **JSON-friendly instruction following**, since this app
   depends heavily on well-formed JSON output.
7. Check plan/quota limits (Lite plan = limited resource units per month) — this project
   makes many LLM calls per document (chunking + planning + slide generation), so confirm
   your plan can sustain expected volume before cutting over.

**Deliverable:** IBM Cloud API key, watsonx project ID, region/service URL, chosen model ID(s).

---

## Phase 2 — SDK & Dependency Changes

1. Add the official SDK to [requirements.txt](requirements.txt):
   ```
   ibm-watsonx-ai>=1.1.0
   ```
2. Keep `groq>=0.9.0` temporarily during migration (see Phase 7, feature-flag rollback),
   remove it only after watsonx is fully validated in production.
3. `pip install ibm-watsonx-ai` locally and confirm import works:
   `from ibm_watsonx_ai import Credentials, APIClient`
   `from ibm_watsonx_ai.foundation_models import ModelInference`

---

## Phase 3 — Configuration (`config.py`) Changes

Add new watsonx settings alongside (not yet replacing) the Groq block:

- `WATSONX_API_KEY` — from `.env`
- `WATSONX_PROJECT_ID` — from `.env`
- `WATSONX_URL` — region service URL, from `.env` (default to `us-south`)
- `WATSONX_MODEL_ID` — e.g. `ibm/granite-3-8b-instruct`
- `WATSONX_TEMPERATURE`, `WATSONX_MAX_TOKENS_PLAN`, `WATSONX_MAX_TOKENS_SLIDE` — mirror the
  existing Groq tuning knobs
- `WATSONX_MAX_RETRIES` — reuse the existing `LLM_MAX_RETRIES` pattern
- `LLM_PROVIDER` — new switch (`"groq"` or `"watsonx"`, default `"groq"` until cutover),
  used later as a feature flag (see Phase 7)
- Multiple-key equivalent: watsonx round-robins less naturally than Groq (auth is per
  IBM Cloud API key, quota is per account/project, not per key). Decide whether to:
  - (a) drop multi-key round robin entirely (simplify `KeyManager`), or
  - (b) support multiple **projects** (each with its own API key + project ID) for
    parallel throughput, rotating similarly to today's `GROQ_API_KEYS` list.

Update `.env` / `.env.example` with the new variables and remove/deprecate Groq-only ones
once migration is complete.

---

## Phase 4 — New watsonx Client Wrapper

Create `llm/watsonx_client.py` as a **drop-in replacement** for `llm/groq_client.py`,
preserving the same public surface so call sites don't change:

- Class `WatsonxClient` with constructor params mirroring `GroqClient`
  (`api_key`, `project_id`, `url`, `model`, `temperature`, `max_tokens`, `max_retries`).
- Internally build `Credentials(url=..., api_key=...)` → `APIClient(credentials, project_id=...)`
  → `ModelInference(model_id=..., api_client=client, params={...})`.
- Implement `chat_complete(messages, temperature, max_tokens) -> str`:
  - Use `ModelInference.chat(messages=[...])` if the chosen model supports the chat API
    (preferred, since this app already builds `role`/`content` message lists), otherwise
    fall back to `generate_text(prompt=...)` with a manually-flattened prompt for
    completion-only models.
- Implement `chat_complete_json(...)` by **reusing** the existing JSON-extraction/retry
  logic (`_extract_json_from_text`, `parse_json_response`, correction-prompt retry loop) —
  move those helper functions into a shared module (e.g. `llm/json_utils.py`) so both
  `groq_client.py` and `watsonx_client.py` import the same parsing code instead of
  duplicating it.
- Map SDK exceptions to the same exception names used today so `except` clauses in
  `app.py` keep working, e.g.:
  - `WatsonxAuthError` (invalid API key / IAM token failure)
  - `WatsonxRateLimitError` (HTTP 429 / quota exceeded)
  - `WatsonxAPIError` (other 4xx/5xx, network errors)
  - Reuse the shared `JSONParseError`
- Note: IBM's IAM bearer token expires (~1 hour) — the SDK's `APIClient` handles refresh
  automatically, so no manual token-refresh logic should be needed, but confirm this
  behavior with a long-running test (see Phase 8).

---

## Phase 5 — Key/Client Manager Changes

Update `llm/key_manager.py` (or add a parallel `llm/watsonx_key_manager.py`):

- Rename concept from "API key round robin" to "credential round robin" if supporting
  multiple projects (Phase 3 option b), or simplify to a single-credential `get_client()`
  if not.
- `KeyManager.from_config()` equivalent should read the new `WATSONX_*` config values.
- Keep the same public method names (`get_client(chunk_index=...)`) so call sites in
  `core/*.py` don't need structural changes — only the import path changes.

---

## Phase 6 — Call-Site Updates (imports only, no logic changes expected)

Each of these files imports `GroqClient` and/or `JSONParseError` directly and will need
the import swapped to the new client (logic/prompts stay the same since both providers
receive the same `messages` list and are expected to return the same JSON shape):

- [core/content_analyzer.py](core/content_analyzer.py)
- [core/presentation_planner.py](core/presentation_planner.py)
- [core/presentation_planner_v3.py](core/presentation_planner_v3.py)
- [core/presentation_planner_template1.py](core/presentation_planner_template1.py)
- [core/slide_generator.py](core/slide_generator.py)
- [core/chunk_analyzer.py](core/chunk_analyzer.py)
- [core/consolidator.py](core/consolidator.py)
- [core/document_structure.py](core/document_structure.py)
- [core/dynamic_chunker.py](core/dynamic_chunker.py)

If a provider feature flag is kept (Phase 7), these files should import a thin factory
(e.g. `llm.client_factory.get_llm_client(...)`) instead of hardcoding `GroqClient`, so the
provider can be swapped via config without touching every call site again in the future.

---

## Phase 7 — UI Updates (`app.py`)

- Sidebar branding: "Powered by Groq Cloud" → "Powered by IBM watsonx.ai" (or provider-agnostic wording).
- Replace "🔑 Groq API Keys" input section with watsonx credential inputs
  (API key + project ID, or just API key if project ID stays server-side/.env only).
- Replace the Groq model dropdown (`groq/compound`, `groq/compound-mini`, etc.) with the
  watsonx model IDs decided in Phase 1.
- Update exception imports/handling (`GroqRateLimitError`, `GroqAPIError` →
  `WatsonxRateLimitError`, `WatsonxAPIError`, or shared provider-neutral exception names).
- Optional feature flag: add a provider selector (`Groq` / `watsonx.ai`) in the sidebar,
  backed by `config.LLM_PROVIDER`, so both providers can run side-by-side during
  validation instead of a hard cutover.

---

## Phase 8 — Testing & Validation

1. Unit-level: run each pipeline stage (chunk analysis → content analysis → planning →
   slide generation) against a small sample document with `LLM_PROVIDER=watsonx` and
   confirm JSON schema validation (`core/validator.py`) still passes.
2. Compare output quality/consistency against the existing Groq baseline for the same
   input document (side-by-side diff of generated `.pptx`).
3. Load test: verify behavior under the existing multi-chunk parallel/sequential flow —
   confirm IAM token refresh and rate-limit handling behave correctly over a long batch.
4. Failure-mode tests: invalid API key, invalid project ID, network timeout, malformed
   JSON response — confirm each maps to a clear, user-facing error in `app.py`.
5. Cost/quota check: confirm token usage per document run stays within the watsonx plan's
   monthly resource-unit budget.

---

## Phase 9 — Cutover & Cleanup

1. Set `LLM_PROVIDER=watsonx` as the default in `.env.example` / deployment config.
2. Update docs: [README.md](README.md), [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md),
   [architecture_overview.md](architecture_overview.md) — replace Groq references with
   watsonx.ai, update setup instructions (IBM Cloud account, API key, project ID) instead
   of the current Groq API key instructions.
3. Once watsonx is confirmed stable in production, remove the Groq dependency
   (`groq` package), delete/retire `llm/groq_client.py` and Groq-only config vars, and
   drop the provider feature flag if no longer needed.
4. Rotate/revoke any Groq API keys that were in use, since they'll no longer be needed.

---

## Open Decisions to Confirm Before Implementation

- [ ] Which watsonx foundation model(s) to standardize on (quality vs. cost vs. latency)?
- [ ] Keep a provider feature flag long-term (multi-provider support) or hard cutover?
- [ ] Multi-credential round robin needed, or is a single API key/project sufficient?
- [ ] Chat API (`ModelInference.chat`) vs. text-completion API (`generate_text`) — depends
      on chosen model's supported interface.
- [ ] Where should the shared JSON-extraction helper (`llm/json_utils.py`) live so both
      clients (or just the new one, if Groq is removed immediately) can reuse it?
