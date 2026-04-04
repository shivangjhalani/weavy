# How to Use Arakne

## What Works Right Now

- Store voice journal transcripts as canonical records
- Run an LLM agent to ingest a transcript into the semantic memory graph
- Ask questions against the graph; agent retrieves and cites source spans
- Themes are automatically maintained after every ingestion and graph-mutating query
- Log fences keep long node histories navigable
- Full run traces saved to disk after every session

**Not yet wired in:** Vector/semantic search is keyword-only until embeddings are generated.

---

## Prerequisites

- **Docker** — FalkorDB runs in a container managed by devenv
- **Gemini API key** — all LLM and (future) embedding calls go through Google AI Studio
- **Groq API key** — only needed when the Whisper transcription CLI is added; optional for now

---

## 1. Setup

```bash
# Copy and fill in your keys
cp .example.env .env
# edit .env — set GEMINI_API_KEY at minimum
```

Start FalkorDB (runs in Docker, persists data under `.devenv/falkordb-data/`):

```bash
devenv up
```

This keeps running in the foreground. Open a second terminal for everything else. FalkorDB's browser UI is available at **http://localhost:3000**.

All commands below are run inside the devenv shell:

```bash
devenv shell
```

Or prefix any single command with `devenv shell --`:

```bash
devenv shell -- uv run python -m arakne.cli <command>
```

---

## 2. Initialise the System Node

Must be done once before anything else:

```bash
uv run python -m arakne.cli init-system
```

This creates the singleton `System` node in FalkorDB that holds global counters and token budgets. Safe to run again — it's idempotent.

Check current state at any time:

```bash
uv run python -m arakne.cli status
```

---

## 3. Transcribe an Audio File

The fastest path. Give it an audio file — it calls Groq Whisper, formats the output with inline `[M:SS]` segment markers, stores it in FalkorDB, and prints the transcript with its new id.

```bash
uv run python -m arakne.cli transcribe /path/to/recording.m4a
```

Output:

```
Transcribing /path/to/recording.m4a ...
Stored as rec:1

[0:00] So I've been thinking about this career decision a lot lately.
[0:14] I know I should probably just quit but the mortgage keeps stopping me.
[0:28] And honestly I think I'm scared of what happens if I actually do it.
[1:05] Had a really good conversation with my mentor yesterday though.
[1:20] She said risk is the only way through.
```

**Supported formats:** `.mp3`, `.mp4`, `.mpeg`, `.mpga`, `.m4a`, `.wav`, `.webm`, `.ogg`

The `[M:SS]` markers become provenance anchors — the ingestion agent uses them to record exactly which seconds of the recording each graph node came from.

Whisper behaviour is controlled by `.env`:

```
WHISPER_MODEL=groq/whisper-large-v3-turbo     # model to use
WHISPER_LANGUAGE=en                            # leave blank for auto-detect
WHISPER_PROMPT=An audio journal...             # context hint improves accuracy
WHISPER_TEMPERATURE=0                          # 0 = deterministic
```

**Alternative: store a pre-existing transcript text file** (if you already have the text):

```bash
uv run python -m arakne.cli create-transcript \
  --audio-path /path/to/audio.m4a \
  --text-file /path/to/transcript.txt
```

List stored transcripts:

```bash
uv run python -m arakne.cli list-transcripts
uv run python -m arakne.cli list-transcripts --limit 5
```

---

## 4. Ingest a Transcript

This runs the ingestion agent against a stored transcript. The agent reads the full text, explores the existing graph, and creates or updates semantic nodes and edges with provenance.

```bash
uv run python -m arakne.cli ingest rec:1
```

The agent will:

1. Read the full transcript
2. Search the existing graph for related nodes
3. Create new nodes or update existing ones, each with a log entry pointing back to the transcript span
4. Call `complete_ingestion` with a natural-language summary
5. After completion: check if any node's hot log exceeds the token budget (creates fences if so), then run the theme agent to update the themes map

Output shows status, touched nodes, and the ingestion summary.

Run traces are saved to `runs/` as JSON — every tool call, touched node, and completion payload is recorded.

---

## 5. Query the Graph

Ask anything in natural language. The agent navigates the semantic graph, retrieves the relevant nodes, traces back to the original transcript spans for evidence, and delivers a grounded answer.

```bash
uv run python -m arakne.cli query "What have I been thinking about recently?"
uv run python -m arakne.cli query "What is the relationship between my career anxiety and my mentor?"
uv run python -m arakne.cli query "What did I say about risk?"
```

The query agent will:

1. Orient using the hot themes block
2. Search the graph and traverse neighborhoods
3. Fetch the exact transcript span(s) as evidence
4. Call `deliver_response` with the answer and citations

A `ChatSession` canonical record is automatically created for every query run, so the conversation is preserved alongside transcripts as a permanent artifact.

If you **correct or add context** during the query ("Actually I already quit that job"), the agent can update the graph in real time using the chat session as provenance. A theme update pass is triggered automatically if any writes occur.

---

## 6. Inspect What's in the Graph

**FalkorDB browser** at http://localhost:3000 — connect to `localhost:6379`, open the `arakne` graph. You can run Cypher queries directly:

```cypher
-- See all semantic nodes
MATCH (n:SemanticNode) RETURN n.id, n.aliases, n.summary LIMIT 20

-- See all themes
MATCH (t:Theme) RETURN t.name, t.state, t.status

-- See a node's full log
MATCH (n:SemanticNode {id: "node:1"}) RETURN n.log

-- See all edges
MATCH (a:SemanticNode)-[r:RELATES]->(b:SemanticNode)
RETURN a.id, r.label, b.id

-- See theme anchors
MATCH (t:Theme)-[:ANCHORS]->(n:SemanticNode)
RETURN t.name, n.id, n.aliases[0]

-- See stored transcripts
MATCH (t:Transcript) RETURN t.id, t.timestamp, t.audio_path

-- See chat sessions created by queries
MATCH (c:ChatSession) RETURN c.id, c.timestamp
```

**Run traces** in `runs/` — each is a JSON file with the full execution record: every tool call, its args and result, touched nodes, completion payload.

---

## 7. Run the Tests

```bash
uv run pytest -v
```

All 100 tests mock the LLM so no API keys are needed. They do require FalkorDB running (the tests use an `arakne_test` graph that is cleaned before each test).

---

## Full CLI Reference

```
uv run python -m arakne.cli <command>

  init-system                  Create the System node (run once)
  status                       Print current System node counters and budgets

  create-transcript            Store a transcript
    --audio-path PATH          Path to the audio artifact (stored as metadata)
    --text-file PATH           Path to the transcript text file

  list-transcripts             List stored transcripts
    --limit N                  Max results (default: 20)

  create-chat                  Store a manually-constructed chat session
    --messages-file PATH       JSON file: [{"role": "user", "content": "..."}, ...]

  list-chats                   List stored chat sessions
    --limit N                  Max results (default: 20)

  transcribe <audio_path>      Transcribe audio and store as a transcript

  ingest <transcript_id>       Run ingestion agent (e.g. rec:1)

  query "<question>"           Run a query/chat session
```

---

## Token Budgets (optional tuning)

Set in `.env` — defaults are shown:

```
LOG_TOKEN_BUDGET=2000        # tokens in a node's hot log before a fence is created
HOT_THEME_TOKEN_BUDGET=250   # tokens for the hot themes block injected into every prompt
```

At ~50-80 tokens per theme, the default 250-token budget fits 3-5 hot themes. Increase if you want more orientation context; decrease to save on input tokens.

---

## Typical First Session

```bash
# 1. Start FalkorDB
devenv up &

# 2. Enter shell
devenv shell

# 3. One-time setup
uv run python -m arakne.cli init-system

# 4. Transcribe an audio recording (needs GROQ_API_KEY in .env)
uv run python -m arakne.cli transcribe /path/to/recording.m4a
# → Stored as rec:1

# 5. Ingest it
uv run python -m arakne.cli ingest rec:1

# 6. Ask something
uv run python -m arakne.cli query "What is stopping me from quitting my job?"
```
