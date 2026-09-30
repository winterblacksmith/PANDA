# PANDA dashboard migration: React + FastAPI

## Outcome

Keep the page interactive while a question, map, or report is being processed.
New answer text should appear progressively; maps should retain their position;
the input, sidebar, and previous answers should remain usable. React alone does
not make inference faster: streaming, background jobs, and isolated UI state
must be designed into the API and frontend.

This is a staged migration plan, not a completed React implementation.

## Recommended stack

- React + TypeScript + Vite for the dashboard, preserving PANDA's forest theme.
- FastAPI for Python APIs. Keep Pandas, Rasterio, PyProj, FVS SQL, and the PDF
  renderer in Python so the numerical and geospatial behavior stays consistent.
- Fetch streaming with server-sent-event framing for answer tokens, progress,
  structured results, errors, and completion. POST supports the question body;
  do not put chat contents in URL query strings. Use AbortController for Stop.
- Leaflet through React-Leaflet for map layers, markers, and polygon selection.
  Keep attribution visible and read basemap configuration through the server.
- TanStack Query for API loading/cache state. Keep map view and draft input in
  separate React state so a new message cannot reset either.
- Start with the existing SQLite database and a single API service/replica on
  the persistent Railway volume. Migrate to PostgreSQL before multiple replicas
  or concurrent public usage requires it. SQLite files cannot be shared safely
  between independent containers as if they were a database server.
- Keep Ollama as a private service with its own model volume. Qwen remains
  qwen2.5:3b initially, allowing like-for-like comparisons.

## Why the current app dims

Streamlit executes the script again after many widget actions. app.py renders
the stored messages and maps again; FVS rendering also executes its SQL query
again for each historical result. Synchronous model calls keep the current run
busy. Removing the dimming CSS would hide the symptom without fixing the work.
The report and connection panels now use fragments; report downloads use
on_click="ignore". The rest of the existing app still follows Streamlit's
rerun model until migrated.

## Phase 1 - Extract and preserve behavior

1. Move file discovery, chat persistence, model access, interpretation, SQL,
   and raster functions out of app.py into Python service modules. None of
   these should import Streamlit or depend on session_state.
2. Pass explicit dataset paths, conversation IDs, selected model, and settings.
3. Keep deterministic SQL filtering and validation separate from the LLM's
   natural-language explanation. Do not execute unrestricted model-written SQL.
4. Replace pickled conversation payloads with versioned JSON records and
   references to result artifacts. Read only trusted existing pickle records
   during the one-time migration; back up SQLite first and verify message counts.
5. Snapshot verified result metrics when the answer is produced. Historical
   answers and reports should not quietly change when the dataset changes.
6. Reuse conversation_report.py behind the future report endpoint.

Acceptance: identical counts, acreage, filters, joins, and coordinate transforms
for the existing regression queries in both the Streamlit and extracted paths.

## Phase 2 - API and job lifecycle

Suggested routes:

| Endpoint | Purpose |
| --- | --- |
| GET /api/datasets | Available datasets, schema, and immutable version ID |
| GET /api/model/status | Server reachable, model installed, last inference error |
| GET/POST /api/conversations | List or create conversations owned by the user |
| GET /api/conversations/{id}/messages | Paginated saved messages and result references |
| POST /api/conversations/{id}/messages | Submit once using a client request ID; return a job ID |
| GET /api/jobs/{id}/events | Progress and answer token stream, resumable by event ID |
| POST /api/jobs/{id}/cancel | Stop generation/query work and persist cancelled state |
| GET /api/results/{id} | Verified metrics, filters, table pages, and layer references |
| GET /api/layers/{id}/tiles/{z}/{x}/{y} | Bounded raster tiles and spatial previews |
| POST /api/conversations/{id}/reports | Build a report from a saved conversation snapshot |
| GET /api/reports/{id}/download | Authorized PDF download |

Use a durable jobs table and a worker for expensive raster/report tasks. Do not
run blocking Rasterio work or synchronous LLM calls on the async event loop.
Apply query timeouts, bounded previews, cancellation, and concurrency limits.
Report generation can take multiple summary calls for long chats; the UI should
display section progress and remain interactive.

Messages and jobs must survive a disconnect. Deduplicate retries by client
request ID. Stream a clear error when Ollama is unavailable; deterministic
results may still be shown with their mode labeled. Do not fabricate an AI reply.

Acceptance: duplicate submit produces one message/job; reconnect resumes the
same answer; cancellation releases the running task; model failure is visible.

## Phase 3 - React dashboard

Build a quiet dataset sidebar, conversation list, chat pane, inline results,
persistent map pane, and report drawer. The empty conversation shows only the
PANDA vector bamboo mark, "What would you like to explore?", and the composer.
No default metrics wall, marketing cards, or technical diagnostics in the main
canvas. Keep those features available behind contextual controls. On narrow
screens, the sidebar becomes a drawer and maps expand within their message.
Stream tokens only into the active answer.
Show progress locally inside the card rather than covering the screen.
Use stable result IDs as keys. Do not remount the map when messages arrive.
Render tables with pagination or virtualization and raster data through tiles
or capped preview images. Never ship a full raster or a huge GeoJSON in chat JSON.

Acceptance: type the next question, pan the map, and read previous answers while
an answer streams. The map view stays unchanged. A cancelled report can be retried.
Test keyboard navigation, narrow screens, and Light/Dark/Forest contrast.

## Phase 4 - Staging, migration, and cutover

Deploy a separate Railway staging frontend, API, and worker against a copy of
the database. Keep Ollama private. The browser contacts only the API. Add
authentication and conversation/dataset ownership checks before shared access;
the current global chat table should not become a public cross-user chat list.
Restrict uploads by file type/size; escape model text and never render raw HTML
from an answer. Keep dataset and report downloads behind the same authorization.

Compare CSV counts, FVS acreage/age charts, MU_ID polygons, TM_Value overlays,
report contents, restart persistence, and model-error behavior. Measure time to
first token, total query time, map payload size, and main-thread responsiveness
before and after. Set performance targets from measurements, not invented gains.

After approval, switch the public URL to React. Keep the Streamlit deployment
available for rollback during validation. Back up before changing storage formats;
do not allow both versions to make incompatible writes to the same database.

## Suggested work order

1. Ship and verify Railway model connectivity + PDF reports (this branch).
2. Extract Python services and their tests.
3. Build streaming chat API with persistent jobs and error states.
4. Build React chat and map layout against the API.
5. Add uploads, saved chats, reports, access controls, and migration tooling.
6. Run parity/load tests, then cut over with a rollback checkpoint.

## References

- React components and state: https://react.dev/learn
- FastAPI streaming and file responses: https://fastapi.tiangolo.com/advanced/custom-response/
- Streamlit fragments: https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- Railway private networking: https://docs.railway.com/networking/private-networking
