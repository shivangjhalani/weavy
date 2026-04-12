# How to Use Weavy

Weavy is a local, CLI-first memory system built on top of:

- FalkorDB for canonical records, semantic graph state, themes, and system counters
- Gemini via LiteLLM for the session agent and theme agent
- Groq Whisper via LiteLLM for audio transcription
- Langfuse for run traces and eval visibility

There is no web app or API layer. The main way to use the app is:

1. Start the backing services
2. Initialize the `System` node
3. Add text (from any source) into the memory graph
4. Query the graph, or continue any prior session

## What Works Right Now

- Add any text into the memory graph via `add` — source-agnostic ingestion
- Transcribe audio with the standalone `transcribe.py` utility as a separate pre-processing step
- Steer ingestion with optional caller context (e.g., "These are chat logs between a user and an AI assistant")
- Ingest text into the semantic graph with provenance-aware node writes
- Ask grounded questions against the graph
- Continue any prior session — ingestion or query — to ask follow-up questions with full context
- A single unified agent handles both ingestion and query, sharing the same tool set and message history model
- Automatic theme maintenance after every `add` — the theme agent self-discovers changes since its last run
- Track agent runs in Langfuse

## What To Expect

- Weavy is synchronous and explicit. If a dependency is missing, it fails loudly rather than silently degrading.
- The graph is a derived memory layer, not the source of truth. Canonical sessions remain the primary records.
- All sessions store their full message history. Ingestion sessions contain the input text + the agent's analysis. Query sessions contain the full conversation.
- Pre-processing is external. Audio transcription, transcript cleanup, and document extraction happen before text reaches Weavy.
- Any session can be continued in query mode — `continue s:N "question"` loads the prior messages as context and runs the query agent.
- Query runs may mutate the graph if the agent decides a new statement should update memory.
- Theme updates run automatically after every `add`. The theme agent queries all sessions completed since its last run and reconciles themes. `update-themes` is available for explicit invocation when needed.
- Run traces are not written to disk. Langfuse is the trace store.

## Prerequisites

You need:

- `devenv`
- Docker
- a Gemini API key
- a Groq API key if you want to use `transcribe`
- a running Langfuse stack if you want tracing

At minimum, copy the example env file:

```bash
cp .example.env .env
```

Then set the values you need:

```env
GEMINI_API_KEY=...
GROQ_API_KEY=...

LANGFUSE_HOST=http://localhost:3100
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

Notes:

- `GROQ_API_KEY` is only required for audio transcription.
- `LANGFUSE_*` is required for tracing. The agent runs without it but you lose observability.
- FalkorDB defaults to `localhost:6379`.
- The default graph name is `weavy`.

## Start The Services

### FalkorDB

The project expects FalkorDB to be available before you use the CLI:

```bash
devenv up
```

Keep that running in one terminal. Open another for commands.

Then enter the environment:

```bash
devenv shell
```

Or prefix a single command:

```bash
devenv shell -- uv run python -m weavy.cli status
```

### Langfuse

Langfuse is used for run tracing. To avoid browser session collisions between the two local UIs, open them on different hostnames:

- FalkorDB UI: `http://127.0.0.1:3000`
- Langfuse UI: `http://localhost:3100`

Start the included local stack with:

```bash
docker compose -f docker-compose.langfuse.yml up -d
```

After Langfuse is up, create or copy your API keys into `.env`.

## Initialize The System Node

Run this once per graph before using the app:

```bash
uv run python -m weavy.cli init-system
```

This creates the singleton `System` node, including:

- next IDs for nodes, edges, and sessions
- `theme_priority_order`
- `hot_theme_token_budget`
- `last_theme_run_at`

Safe to run again — uses `MERGE`.

Inspect current state any time:

```bash
uv run python -m weavy.cli status
```

If the `System` node does not exist, most operations will fail with a message telling you to run `init-system` first.

## Add Text To The Memory Graph

The primary entry point is `add`. It accepts any text — transcripts, chat logs, notes, journal entries, documents — and runs the ingestion agent to integrate it into the semantic graph.

```bash
uv run python -m weavy.cli add /path/to/notes.txt
```

Or pipe from stdin:

```bash
echo "Today I decided to switch to Rust for the backend." | uv run python -m weavy.cli add -
```

What happens:

1. A canonical `Session` is created with the text as the first user message
2. The ingestion agent reads the text, searches the existing graph, and creates/updates semantic nodes and edges
3. The theme agent runs automatically to reconcile themes against the updated graph
4. The CLI prints the session status, touched node IDs, and the ingestion summary

### Caller Context

Use `--context` to steer the agent's interpretation without modifying the prompt:

```bash
uv run python -m weavy.cli add chat-export.txt --context "These are chat sessions between a user and an AI assistant"
```

The context is injected into the system prompt as `- **Caller context:** <value>`. When omitted, the slot resolves to empty string. The agent reads the text and determines what it is on its own.

### Timestamps

Use `--timestamp` to set the session timestamp (defaults to now):

```bash
uv run python -m weavy.cli add journal.txt --timestamp 2026-04-01T10:00:00+00:00
```

## Transcribe Audio

Transcription is a standalone pre-processing utility. It does not ingest into Weavy directly:

```bash
python transcribe.py /path/to/recording.m4a
```

What happens:

- The file is sent to Groq Whisper through LiteLLM
- The raw Whisper response is written to stdout as JSON, or to a file with `--output`
- You decide how to extract or format the text before sending it to `weavy add`

Supported audio extensions: `.mp3`, `.mp4`, `.mpeg`, `.mpga`, `.m4a`, `.wav`, `.webm`, `.ogg`

Write JSON to a file:

```bash
python transcribe.py recording.m4a --output transcript.json
```

Important behavior:

- Missing files raise `FileNotFoundError`
- Unsupported extensions raise `ValueError`
- This script has no dependency on the memory graph or Weavy session model

Whisper-related env vars:

```env
WHISPER_MODEL=groq/whisper-large-v3-turbo
WHISPER_LANGUAGE=
WHISPER_PROMPT=
WHISPER_TEMPERATURE=0
```

Typical workflow:

1. Transcribe audio with `transcribe.py`
2. Extract or format the text you want to keep
3. Pass that text to `uv run python -m weavy.cli add ...`

### List Stored Sessions

```bash
uv run python -m weavy.cli list-sessions
uv run python -m weavy.cli list-sessions --limit 5
```

Output includes session ID, timestamp, and summary (if ingested):

```text
s:1  2026-04-04T12:34:56+00:00  Ingested notes about career planning.
s:2  2026-04-05T10:15:00+00:00  (not yet ingested)
```

## Continue Any Session

After adding content, you can continue that session to ask questions with the full text + agent analysis as context:

```bash
uv run python -m weavy.cli continue s:1 "What did I say about my mortgage?"
```

This always runs in query mode — the query agent is given the session's existing message history plus your new question. It can search the graph and answer based on both the stored graph and the conversation context.

This works on any session — ingestion or query — making every conversation resumable.

## Query The Graph

Run a one-shot query (creates a new session):

```bash
uv run python -m weavy.cli query "What have I been thinking about recently?"
```

What query mode does:

1. Mints a new session
2. Builds the system prompt from `weavy-query.md` plus hot themes
3. Lets the agent search the graph, inspect neighborhoods, and retrieve source evidence
4. Finalizes with `complete`
5. Persists the full conversation as a canonical `Session`

What the CLI prints:

- `Status: completed` or `Status: failed`
- the final answer if successful

### Interactive Chat Mode

Omit the question argument to start a REPL:

```bash
uv run python -m weavy.cli query
```

```text
Weavy chat — type 'exit' or Ctrl-D to quit.
```

Behavior to expect:

- one session (`s:N`) is created for the full REPL session
- each turn calls the query agent with the full accumulated history, loaded from FalkorDB
- history is persisted after each turn so the session is crash-safe
- if a turn fails, the REPL prints the error and continues

## Themes

Theme maintenance runs automatically after every `add` call. You do not need to invoke it manually.

The theme agent is self-discovering. It queries all sessions completed since its last run (tracked via `last_theme_run_at` on the System node) and builds a journal of recent activity.

What the theme agent receives:

- the current full theme map
- a session journal listing each completed session's summary and graph changes

What to expect:

- new themes may be created
- existing themes may be updated or retired
- `theme_priority_order` on the `System` node may change
- `last_theme_run_at` is updated after a successful run

## Tracing And Langfuse

Each harness run creates a Langfuse trace with nested spans for:

- the run root
- each turn
- each LLM generation
- each tool call

These are not saved locally. If you want to inspect a run, use the Langfuse UI.

### Prompts

Agent prompts live in `weavy/prompts/` as local markdown files:

- `weavy-ingestion.md` — ingestion agent prompt (source-agnostic, uses `{{caller_context}}` for steering)
- `weavy-query.md` — query/chat agent prompt
- `weavy-theme.md` — theme maintenance prompt

Template variables (e.g. `{{session_id}}`, `{{themes_context}}`, `{{caller_context}}`) are replaced at runtime.

## Inspect The Database

FalkorDB is available on `localhost:6379`. Useful Cypher queries:

```cypher
MATCH (n:SemanticNode)
RETURN n.id, n.aliases, n.summary
LIMIT 20
```

```cypher
MATCH (t:Theme)
RETURN t.name, t.state, t.status
```

```cypher
MATCH (s:Session)
RETURN s.id, s.timestamp, s.completed_at, s.summary
ORDER BY s.timestamp DESC
```

```cypher
MATCH (s:System) RETURN s
```

## Full CLI Reference

All commands run through:

```bash
uv run python -m weavy.cli <command>
```

Commands:

```text
init-system
status

list-sessions [--limit N]

add <file_or_-> [--context "..."] [--timestamp ISO]
continue <session_id> <question>
update-themes
set-preface <preface>
query [question]
```

## Common Failure Modes

### `System node not found`

```bash
uv run python -m weavy.cli init-system
```

### Tracing failures

Check that Langfuse is running and `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` are set.

### Transcription failures

Check that `GROQ_API_KEY` is set, the file exists, and the extension is supported.

### LLM or query failures

Check that `GEMINI_API_KEY` is set and the graph is reachable.

## Shortest Happy Path

```bash
cp .example.env .env
# fill in GEMINI_API_KEY, GROQ_API_KEY, LANGFUSE_* as needed

devenv up
docker compose -f docker-compose.langfuse.yml up -d

devenv shell
uv run python -m weavy.cli init-system
uv run python -m weavy.cli add notes.txt --context "Personal journal entry"
uv run python -m weavy.cli query "What has been on my mind recently?"
uv run python -m weavy.cli continue s:1 "Tell me more about what I said about X"

# audio transcription is a separate preprocessing step:
python transcribe.py /path/to/recording.m4a --output transcript.json
```
