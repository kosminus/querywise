# Assistant Panel — Implementation Plan

A conversational "Assistant" on the `/query` page. Users ask questions (→ existing
NL-to-SQL pipeline) and add glossary terms by talking (→ structured draft →
confirmation card → existing glossary REST POST). REST inside the app; MCP stays
external-only.

## Principles

- **One stateless endpoint**, one structured-JSON LLM call per turn. No tool-calling
  loop, no provider changes, no chat-session table (history passed from the client).
- **The assistant never writes.** It only *drafts*. Every write rides the existing
  `POST /connections/{id}/glossary` (auth + auto-embed unchanged). So the assistant
  endpoint needs only **read** auth.
- **Discriminated action union** from day one (`glossary_draft | sql_preview`), so
  `metric_draft` etc. are new cards later, not a refactor.
- **Reuse, don't re-derive:** `sql_preview` → existing `generate_sql_only`;
  executing it → existing `execute_raw_sql` (`/query/execute-sql`).

## Flow

```
user message ──► POST /connections/{id}/assistant  (require_connection_read)
                      │
                      ├─ build_context(db, id, message)         # existing
                      ├─ AssistantAgent.route(message, ctx, history)  # 1 LLM call
                      │     └─► {intent: question|glossary|chat, message, glossary?}
                      │
                      ├─ intent=question → generate_sql_only()  # existing, 2nd LLM call
                      │     └─► action = sql_preview {sql, explanation}
                      ├─ intent=glossary → action = glossary_draft {term,...}
                      │     └─ (if caller lacks write → downgrade to chat message)
                      └─ intent=chat    → no action
                      ▼
        { message: string, action?: {type, payload} }
                      │
   frontend renders a card:
     glossary_draft → editable card → [Create] → glossaryApi.create()  → invalidate glossary
     sql_preview    → SQL card      → [Execute] → queryApi.executeSql() → results inline
```

## Backend

### 1. Prompt — `app/llm/prompts/assistant_prompts.py` (new)
System + user template instructing the model to return JSON:
```json
{
  "intent": "question | glossary | chat",
  "message": "natural-language reply to show the user",
  "glossary": {
    "term": "...", "definition": "...", "sql_expression": "...",
    "related_tables": ["..."], "related_columns": ["..."]
  }
}
```
- `glossary` present only when `intent == "glossary"`.
- Ground `related_tables`/`related_columns` and the `sql_expression` against the
  assembled semantic context (real table/column names), same context string the
  composer uses.

### 2. Agent — `app/llm/agents/assistant_router.py` (new)
Mirror `QueryComposerAgent`: `__init__(provider, config)`, `async route(message, context, history) -> AssistantDecision`.
- `provider.complete(messages, config)` then `json.loads(repair_json(...))` with a
  safe fallback (`intent="chat"`, echo message) on `JSONDecodeError`.
- `@dataclass AssistantDecision: intent: str; message: str; glossary: dict | None`.

### 3. Service — `app/services/assistant_service.py` (new)
```python
async def handle_turn(db, connection_id, message, history, ctx) -> dict:
    conn = await get_connection(db, connection_id, ctx)          # read-authz
    context = await build_context(db, connection_id, message, dialect=conn.connector_type)
    provider, llm_config = route(message)
    decision = await AssistantAgent(provider, llm_config).route(message, context.prompt_context, history)

    if decision.intent == "question":
        sql = await generate_sql_only(db, connection_id, message, ctx)
        return {"message": decision.message,
                "action": {"type": "sql_preview",
                           "payload": {"sql": sql["generated_sql"],
                                       "explanation": sql["explanation"]}}}

    if decision.intent == "glossary" and decision.glossary:
        if not await _can_write(db, connection_id, ctx):         # viewer downgrade
            return {"message": "You need editor access to add glossary terms."}
        return {"message": decision.message,
                "action": {"type": "glossary_draft", "payload": decision.glossary}}

    return {"message": decision.message}                         # chat
```
- `_can_write`: `try: await get_connection(db, id, ctx, write=True); return True / except AppError: return False`
  (or read `ctx` role rank if exposed on `AuthContext`).

### 4. Schemas — `app/api/v1/schemas/assistant.py` (new)
- `AssistantMessage{role: Literal["user","assistant"], content: str}`
- `AssistantRequest{message: str, history: list[AssistantMessage] = []}`
- `GlossaryDraft{term, definition, sql_expression, related_tables=[], related_columns=[]}`
  (shape matches `GlossaryTermCreate` minus `examples`)
- `SqlPreviewPayload{sql, explanation}`
- `AssistantAction` = discriminated union on `type` (`glossary_draft` | `sql_preview`)
- `AssistantResponse{message: str, action: AssistantAction | None = None}`

### 5. Endpoint — `app/api/v1/endpoints/assistant.py` (new) — AS BUILT
```python
router = APIRouter(prefix="/query", tags=["assistant"])

@router.post("/assistant", response_model=AssistantResponse)
async def assistant_turn(body: AssistantRequest,
                         ctx=Depends(get_org_context), db=Depends(get_db)):
    history = [m.model_dump() for m in body.history]
    return AssistantResponse(**await assistant_service.handle_turn(
        db, body.connection_id, body.message, history, ctx))
```
- **Mounted under `/query`** with `connection_id` in the body, using `get_org_context` —
  mirrors the existing query endpoints exactly. The service's `get_connection` enforces
  read-authz. Chosen over a `/connections/{id}/assistant` path route because the existing
  rate limiter is scoped to `/api/v1/query/*`, so the assistant gets rate-limiting for
  free and stays consistent with `/query`, `/query/sql-only`, `/query/execute-sql`.
- Registered in `app/api/v1/router.py` (`assistant.router`).
- Rate limiting: no code change needed — `/api/v1/query/assistant` already matches the
  `/query` prefix scope in `install_rate_limiting`.

### Backend tests — `backend/tests/`
- Agent: feed canned provider responses (question / glossary / chat / malformed JSON) →
  assert `AssistantDecision`.
- Service: monkeypatch agent + `build_context`; assert action shapes and viewer downgrade.

## Frontend

### 6. Types — `frontend/src/types/api.ts` (extend)
`GlossaryDraft`, `SqlPreviewPayload`, `AssistantAction` (discriminated on `type`),
`AssistantResponse`, `AssistantChatMessage{role, content, action?}`.

### 7. API client — `frontend/src/api/assistantApi.ts` (new)
```ts
export const assistantApi = {
  send: (connectionId: string, data: { message: string; history: {role:string;content:string}[] }) =>
    api.post<AssistantResponse>(`/connections/${connectionId}/assistant`, data).then(r => r.data),
};
```

### 8. Extract reusable result view
Pull `QueryResultView` out of `QueryPage.tsx` into
`frontend/src/components/query/QueryResultView.tsx` so the assistant's `sql_preview`
execution can render results with the same component.

### 9. Component — `frontend/src/components/assistant/AssistantPanel.tsx` (new)
Props: `{ connectionId: string }`.
- Local `messages: AssistantChatMessage[]` state; input box; `useMutation` →
  `assistantApi.send(connectionId, { message, history: last N })`.
- On response: append assistant message; if `action`, render the matching card:
  - **GlossaryDraftCard** — editable fields (term, definition, sql_expression,
    related_tables, related_columns). `[Create]` → `glossaryApi.create(connectionId, draft)`,
    on success show confirmation + `queryClient.invalidateQueries(['glossary', connectionId])`.
    `[Dismiss]` to discard.
  - **SqlPreviewCard** — show SQL (Monaco/`Code`). `[Execute]` →
    `queryApi.executeSql({connection_id, sql, original_question})` → render `<QueryResultView/>`
    in the thread. `[Edit]`/`[Cancel]` like the existing preview.
- Gate by role: hide the panel (or show read-only) for viewers via `useAuth().role`
  rank; server already downgrades glossary drafts regardless.

### 10. Mount on QueryPage — `frontend/src/pages/QueryPage.tsx`
Add `<AssistantPanel connectionId={connectionId} />` as a side/below section. Inherits
the already-selected connection — no new connection selector. Defer the app-wide drawer.

## Implemented draft intents
- `glossary` → `glossary_draft` → `POST /connections/{id}/glossary`
- `metric` → `metric_draft` → `POST /connections/{id}/metrics`
- `dictionary` → `dictionary_draft` → `POST /columns/{column_id}/dictionary` (per entry).
  The service resolves `(table_name, column_name) → column_id` against the schema cache
  (`_resolve_column_id`) and downgrades to a chat message if the column isn't found.
  Drafts carry MULTIPLE value entries for one column.
- `knowledge` → `knowledge_draft` → `POST /connections/{id}/knowledge`
- `question` → `sql_preview` → `POST /query/execute-sql`

All draft intents are editor-gated (`ctx.has_role(ROLE_EDITOR)`); viewers get questions only.
The agent returns a generic `AssistantDecision{intent, message, payload}`; per-intent
normalizers in `assistant_router.py` validate/shape the payload (and downgrade to chat if
unusable).

## Out of scope (intentionally deferred)
- Sample-query drafts (same pattern — would be a 6th card).
- Persisted chat sessions (history + audit) and the app-wide drawer.
- True tool-calling agent loop (provider `tools=` support).

## File summary
**New:** `assistant_prompts.py`, `assistant_router.py`, `assistant_service.py`,
`schemas/assistant.py`, `endpoints/assistant.py`, `assistantApi.ts`,
`components/assistant/AssistantPanel.tsx`, `components/query/QueryResultView.tsx`.
**Edit:** `api/v1/router.py`, rate-limit wiring, `types/api.ts`, `QueryPage.tsx`.
