---
phase: quick
plan: 260401-pbt
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
autonomous: true
requirements: [MEMO-01]
must_haves:
  truths:
    - "MEMO-01 exists as a v1 requirement in a 'Memo Agent' section, not in v2"
    - "MEMO-01 is mapped to Phase 2 in the traceability table"
    - "ROADMAP Phase 2 requirements list includes MEMO-01"
    - "v1 coverage count reads 38, not 37"
  artifacts:
    - path: ".planning/REQUIREMENTS.md"
      provides: "MEMO-01 promoted to v1 with correct scope"
      contains: "MEMO-01"
    - path: ".planning/ROADMAP.md"
      provides: "Phase 2 requirements list includes MEMO-01"
      contains: "MEMO-01"
  key_links: []
---

<objective>
Promote memo mode (MEMO-01) from v2 to v1 in REQUIREMENTS.md and update ROADMAP.md Phase 2 to include it.

Purpose: Memory-v5.md (the design doc) treats memo mode as a first-class harness mode alongside ingestion, query, and theme -- same loop, different system prompt. HARN-01 already specifies "ingestion, query, and theme modes via system prompt swap" but the memo requirement was incorrectly deferred to v2. This fix aligns the requirements with the design doc.

Output: Patched REQUIREMENTS.md and ROADMAP.md
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@markdowns/Memory-v5.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Promote MEMO-01 to v1 and update traceability</name>
  <files>.planning/REQUIREMENTS.md, .planning/ROADMAP.md</files>
  <action>
  Patch .planning/REQUIREMENTS.md with these EXACT changes (do NOT alter anything else):

  1. **Add "Memo Agent" section in v1** — Insert a new section after "### Query Agent" (after line 63, before "### Privacy & Data") with this content:

     ```
     ### Memo Agent

     - [ ] **MEMO-01**: Memo mode runs the shared harness (HARN-01) with a different system prompt — the agent takes the voice of a thoughtful observer noticing patterns across sessions and writes memos unprompted; it is not a separate runtime
     ```

  2. **Remove MEM-01 from v2** — Delete line 86 (`- **MEM-01**: Memo mode — observer agent that notices patterns and writes memos unprompted`). Leave MEM-02 in v2 "Advanced Memory" as-is.

  3. **Add MEMO-01 to traceability table** — Insert a row `| MEMO-01    | Phase 2 | Pending |` in the traceability table. Place it after the QUERY-04 row (line 148) and before the PRIV-01 row, to keep Phase 2 requirements grouped together.

  4. **Update coverage count** — Change line 154 from `- v1 requirements: 37 total` to `- v1 requirements: 38 total`. Change line 155 from `- Mapped to phases: 37` to `- Mapped to phases: 38`.

  5. **Update "Last updated" line** — Change the last line from `_Last updated: 2026-04-01 after initial definition_` to `_Last updated: 2026-04-01 after promoting MEMO-01 from v2 to v1_`.

  Then patch .planning/ROADMAP.md with these EXACT changes (do NOT alter anything else):

  6. **Add MEMO-01 to Phase 2 Requirements** — On line 40, append `, MEMO-01` after `QUERY-04` so it reads:
     `**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, THEME-01, THEME-02, THEME-03, THEME-04, QUERY-01, QUERY-02, QUERY-03, QUERY-04, MEMO-01`

  7. **Update coverage line** — Change line 3 from `**Coverage:** 37/37 v1 requirements mapped` to `**Coverage:** 38/38 v1 requirements mapped`.

  8. **Update "Last updated" line** — Change the last line to `*Last updated: 2026-04-01 after adding MEMO-01 to Phase 2*`.

  CRITICAL: Do not change any other content. Every other requirement, section, and line must remain exactly as-is.
  </action>
  <verify>
    <automated>cd /home/shivang/shivang/projs/arachne && grep -c "MEMO-01" .planning/REQUIREMENTS.md | grep -q "3" && grep -c "MEMO-01" .planning/ROADMAP.md | grep -q "1" && grep "38 total" .planning/REQUIREMENTS.md && grep "38/38" .planning/ROADMAP.md && ! grep "MEM-01" .planning/REQUIREMENTS.md | grep -q "v2" && echo "PASS" || echo "FAIL"</automated>
  </verify>
  <done>
    - MEMO-01 appears in v1 "Memo Agent" section of REQUIREMENTS.md with correct description referencing HARN-01 and system prompt swap
    - MEM-01 is removed from v2 "Advanced Memory" section (MEM-02 remains)
    - MEMO-01 row exists in traceability table mapped to Phase 2
    - Coverage reads "38 total" and "Mapped to phases: 38"
    - ROADMAP Phase 2 Requirements line includes MEMO-01
    - ROADMAP coverage reads "38/38"
    - No other content changed in either file
  </done>
</task>

</tasks>

<verification>
- `grep "MEMO-01" .planning/REQUIREMENTS.md` returns 3 hits: section header area, traceability table, and the requirement itself
- `grep "MEM-01" .planning/REQUIREMENTS.md` returns exactly 1 hit (MEM-02 line only mentions MEM-02, not MEM-01)
- `grep "MEMO-01" .planning/ROADMAP.md` returns 1 hit in Phase 2 Requirements
- `grep "38" .planning/REQUIREMENTS.md` shows updated count
- `grep "38/38" .planning/ROADMAP.md` shows updated coverage
- `git diff` shows only the expected lines changed
</verification>

<success_criteria>
MEMO-01 is a v1 requirement in the "Memo Agent" section, mapped to Phase 2 in both REQUIREMENTS.md and ROADMAP.md. MEM-01 no longer exists in v2. All counts updated to 38. No other content changed.
</success_criteria>

<output>
After completion, create `.planning/quick/260401-pbt-fix-memo-mode-scope-mismatch-in-requirem/260401-pbt-SUMMARY.md`
</output>
