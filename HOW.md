# How to Use Weavy

Weavy is a local, CLI-first memory system built on top of:

- FalkorDB for canonical records, semantic graph state, themes, and system counters
- Gemini via LiteLLM for ingestion, query, and theme agents
- Groq Whisper via LiteLLM for audio transcription
- Langfuse for prompt management, run traces, and eval visibility

There is no web app or API layer in this repo right now. The main way to use the app is:

1. Start the backing services
2. Initialize the `System` node
3. Create or transcribe transcripts
4. Ingest those transcripts into the graph
5. Query the graph from the CLI

## What Works Right Now

- Store transcripts as canonical `Transcript` records
- Transcribe audio into `[M:SS]`-annotated transcript text
- Ingest a transcript into the semantic graph with provenance-aware node writes
- Ask grounded questions against the graph
- Persist chat sessions as canonical `ChatSession` records
- Automatically run theme maintenance after ingestion and graph-mutating query sessions
- Track agent runs and prompt versions in Langfuse
- Run eval scenarios through Langfuse-backed datasets

## What To Expect

- Weavy is synchronous and explicit. If a dependency is missing, it tends to fail loudly rather than silently degrading.
- The graph is a derived memory layer, not the source of truth. Canonical transcripts and chats remain the primary records.
- Query runs may mutate the graph if the agent decides your new statement should update memory.
- Theme updates are automatic after completed runs that touched graph nodes.
- Long node histories are compacted by fence checks using the configured token budget.
- Run traces are not written to disk. Langfuse is the trace store.
- Prompt loading is Langfuse-backed. If Langfuse is not running or prompts are not seeded, ingestion/query/theme runs will fail.

## Prerequisites

You need:

- `devenv`
- Docker
- a Gemini API key
- a Groq API key if you want to use `transcribe`
- a running Langfuse stack if you want ingestion/query/theme/evals to work

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
- `LANGFUSE_*` is required for prompt fetches and tracing.
- FalkorDB defaults to `localhost:6379`.
- The default graph name is `arakne`.

## Start The Services

### FalkorDB

The project expects FalkorDB to be available before you use the CLI:

```bash
devenv up
```

Keep that running in one terminal. Open another terminal for commands.

Then enter the environment:

```bash
devenv shell
```

Or prefix a single command:

```bash
devenv shell -- uv run python -m weavy.cli status
```

### Langfuse

Langfuse is effectively part of the app flow now because prompts are fetched from it and traces are recorded there.

To avoid browser session collisions between the two local UIs, open them on different hostnames:

- FalkorDB UI: `http://127.0.0.1:3000`
- Langfuse UI: `http://localhost:3100`

You can start the included local stack with:

```bash
docker compose -f docker-compose.langfuse.yml up -d
```

The UI is available at:

```text
http://localhost:3100
```

After Langfuse is up, create or copy your API keys into `.env`, then seed the prompts:

```bash
uv run python scripts/seed_prompts.py
```

What this does:

- creates or updates the `weavy-ingestion` prompt
- creates or updates the `weavy-query` prompt
- creates or updates the `weavy-theme` prompt
- tags them with the `production` label

If prompts are missing, ingestion and query runs will fail when `fetch_prompt()` tries to load them.

## Initialize The System Node

Run this once per graph before using the app:

```bash
uv run python -m arakne.cli init-system
```

This creates the singleton `System` node, including:

- next ids for nodes, edges, transcripts, and chats
- `theme_priority_order`
- `log_token_budget`
- `hot_theme_token_budget`

Safe to run again. It uses `MERGE`.

Inspect current state any time:

```bash
uv run python -m weavy.cli status
```

If the `System` node does not exist, many operations will fail with a message telling you to run `init-system` first.

## Create Or Transcribe Transcripts

Arakne ingests stored transcripts, not raw audio directly. You have two main paths.

### Option 1: Transcribe Audio

```bash
uv run python -m arakne.cli transcribe /path/to/recording.m4a
```

What happens:

- the file is sent to Groq Whisper through LiteLLM
- the response is normalized into transcript lines with inline `[M:SS]` markers
- a canonical `Transcript` is created in FalkorDB
- the CLI prints the new `rec:N` id and the transcript text

Supported audio extensions:

- `.mp3`
- `.mp4`
- `.mpeg`
- `.mpga`
- `.m4a`
- `.wav`
- `.webm`
- `.ogg`

Important behavior:

- missing files raise `FileNotFoundError`
- unsupported extensions raise `ValueError`
- the transcription call always asks for `verbose_json`
- the stored transcript is plain text with inline timestamps

Example output:

```text
Transcribing /path/to/recording.m4a ...
Stored as rec:1

[0:00] I've been thinking about changing jobs a lot lately.
[0:14] The mortgage scares me but I'm feeling trapped.
[0:28] Had a great talk with my mentor yesterday about risk.
```

Whisper-related env vars:

```env
WHISPER_MODEL=groq/whisper-large-v3-turbo
WHISPER_LANGUAGE=
WHISPER_PROMPT=
WHISPER_TEMPERATURE=0
```

### Option 2: Create A Transcript From Existing Text

If you already have transcript text:

```bash
uv run python -m arakne.cli create-transcript \
  --audio-path /path/to/original-audio.m4a \
  --text-file /path/to/transcript.txt
```

Notes:

- `--audio-path` is stored as metadata only
- the text file must exist
- the CLI creates a new `rec:N`

### List Stored Transcripts

```bash
uv run python -m arakne.cli list-transcripts
uv run python -m arakne.cli list-transcripts --limit 5
```

Expect output shaped like:

```text
rec:1  2026-04-04T12:34:56+00:00  /path/to/audio.m4a
```

## Ingest A Transcript

Once you have a `rec:N`, ingest it:

```bash
uv run python -m arakne.cli ingest rec:1
```

What ingestion does:

1. Loads the transcript from FalkorDB
2. Builds the ingestion system prompt from Langfuse plus current hot-theme context
3. Runs the harness with read/write graph tools
4. Lets the agent search, inspect, create, and update semantic graph entities
5. Requires provenance on every node write
6. Finalizes with `complete_ingestion`
7. Runs post-trace hooks:
   - fence checks on touched live nodes
   - theme update pass

What the CLI prints:

- final run status
- touched node ids
- the ingestion summary

Important expectations:

- ingestion fails if the transcript id does not exist
- ingestion fails if Langfuse prompt fetch fails
- ingestion may create new nodes, update existing nodes, and create/update edges
- provenance is anchored back to transcript time offsets, so timestamp quality matters

## Query The Graph

Run a one-shot query:

```bash
uv run python -m arakne.cli query "What have I been thinking about recently?"
```

What query mode does:

1. Mints or reuses a `chat:N`
2. Builds the query system prompt from Langfuse plus hot themes
3. Lets the agent search the graph, inspect neighborhoods, and retrieve transcript evidence
4. Finishes via `deliver_response`
5. Persists the conversation as a canonical `ChatSession`
6. If graph nodes were touched, runs fence checks and a theme update

What the CLI prints:

- `Status: completed` or `Status: failed`
- the final answer if successful
- the error if the run failed

### Interactive Chat Mode

If you omit the question argument:

```bash
uv run python -m arakne.cli query
```

Arakne starts a REPL:

```text
Arakne chat — type 'exit' or Ctrl-D to quit.
```

Behavior to expect:

- one `chat:N` is created for the full REPL session
- full prior conversation is fed back into subsequent turns
- on exit, the chat session is persisted if there was any conversation
- if a turn fails, the REPL prints the error and continues

## Chat And Transcript Canonical Records

Arakne keeps canonical records alongside the derived semantic graph.

You can also manually create chat sessions:

```bash
uv run python -m arakne.cli create-chat --messages-file messages.json
```

Where `messages.json` looks like:

```json
[
  { "role": "user", "content": "I think I want to move cities." },
  { "role": "assistant", "content": "What makes that feel urgent right now?" }
]
```

List stored chats:

```bash
uv run python -m arakne.cli list-chats
uv run python -m arakne.cli list-chats --limit 10
```

## Themes And Automatic Post-Run Behavior

Theme maintenance is not a top-level CLI command. It runs automatically after:

- a completed ingestion that touched nodes
- a completed query/chat run that touched nodes

What the theme pass receives:

- the completion summary or answer text
- touched node ids and actions
- touched edge ids and actions
- the current full theme map

What to expect:

- new themes may be created
- existing themes may be updated or retired
- `theme_priority_order` on the `System` node may change

## Tracing, Prompts, And Langfuse

Langfuse is used for three distinct jobs:

- prompt storage and versioning
- run traces
- eval dataset and experiment visibility

### Traces

Each harness run creates a Langfuse trace with nested spans for:

- the run root
- each turn
- each LLM generation
- each tool call

These are not saved to a local `runs/` folder. If you want to inspect a run, use Langfuse.

### Prompts

Arakne fetches prompts by name from Langfuse with the `production` label:

- `arakne-ingestion`
- `arakne-query`
- `arakne-theme`

If you change prompts in Langfuse, that changes runtime behavior without a code change.

## Inspect The Database

You can inspect FalkorDB directly. The current local setup usually exposes the database on:

```text
localhost:6379
```

Useful example Cypher queries:

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
MATCH (t:Transcript)
RETURN t.id, t.timestamp, t.audio_path
ORDER BY t.timestamp DESC
```

```cypher
MATCH (c:ChatSession)
RETURN c.id, c.timestamp
ORDER BY c.timestamp DESC
```

```cypher
MATCH (t:Theme)-[:ANCHORS]->(n:SemanticNode)
RETURN t.name, n.id, n.aliases[0]
```

## Evals

This repo includes eval execution code, but not a CLI command for it.

The eval flow is Python-level and Langfuse-backed:

- datasets live in Langfuse
- dataset items are loaded into `EvalItem`
- `ingestion`, `query`, and `theme` scenario items are supported
- results are linked back to the Langfuse dataset item as experiment runs

Relevant modules:

- `arakne.evals.scenarios`
- `arakne.evals.runner`
- `arakne.evals.judges`
- `arakne.evals.reports`

## Full CLI Reference

All commands run through:

```bash
uv run python -m arakne.cli <command>
```

Commands:

```text
init-system
status

create-transcript --audio-path PATH --text-file PATH
list-transcripts [--limit N]

create-chat --messages-file PATH
list-chats [--limit N]

transcribe <audio_path>
ingest <transcript_id>
query [question]
```

## Common Failure Modes

### `System node not found`

Run:

```bash
uv run python -m arakne.cli init-system
```

### Prompt fetch or trace failures

Check:

- Langfuse is running
- `LANGFUSE_HOST` is correct
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set
- prompts were seeded with `uv run python scripts/seed_prompts.py`

### Transcription failures

Check:

- `GROQ_API_KEY` is set
- the file exists
- the extension is supported

### LLM or query failures

Check:

- `GEMINI_API_KEY` is set
- the graph is reachable
- Langfuse is available

### Tests failing in this environment

Some test runs may fail before collection if native dependencies used by `litellm` or `tokenizers` are missing from the runtime environment. That is an environment issue, not necessarily an Arakne logic issue.

## Current Limits

- CLI-first only
- no API server
- no UI for normal app usage
- no separate manual theme-update CLI command
- prompt management depends on Langfuse
- semantic/vector behavior depends on the graph/index/runtime setup and may not be fully production-shaped yet

If you want the shortest happy path, use this sequence:

```bash
cp .example.env .env
# fill in GEMINI_API_KEY, GROQ_API_KEY, LANGFUSE_* as needed

devenv up
docker compose -f docker-compose.langfuse.yml up -d

devenv shell
uv run python scripts/seed_prompts.py
uv run python -m arakne.cli init-system
uv run python -m arakne.cli transcribe /path/to/recording.m4a
uv run python -m arakne.cli ingest rec:1
uv run python -m arakne.cli query "What has been on my mind recently?"
```
