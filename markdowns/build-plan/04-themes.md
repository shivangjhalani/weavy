# Theme System Plan

## Goal

Implement themes as a small, derived orientation layer that is updated only from session deltas and rendered into a bounded hot set for future runs.

## Theme Model

Each theme contains:
- `name`
- `state`
- `status`

Anchors are stored only as:
- `(:Theme)-[:ANCHORS]->(:SemanticNode)`

Rules:
- no theme log
- no theme ids
- no anchor arrays persisted on the theme node

## Theme Status

Supported values:
- `deep`
- `active`
- `emerging`
- `dormant`

The code should treat status as a validated categorical field. It should not derive status mechanically in the store layer.

## Theme Update Trigger

Run theme mode synchronously after:
- ingestion runs with graph writes
- query/chat runs with graph writes

Do not run theme mode after:
- read-only query runs
- failed runs

## Theme Mode Input

Theme mode should receive exactly:
- current full themes map
- current `theme_priority_order`
- delta payload from the preceding run
- graph read tools

Delta payload fields:
- `summary`
- `touched_nodes`
- `touched_edges`

Rules:
- touched entities come from harness tracking
- theme mode should not need to reconstruct the delta itself

## Theme Tool Surface

- `get_theme(name)`
- `create_theme(name, state, anchors, status)`
- `update_theme(name, new_state?, new_anchors?, new_status?)`
- `retire_theme(name)`
- `complete_theme_update(updated_themes, priority_order)`

## Hot Theme Rendering

Implement hot-theme rendering as a pure function from:
- full theme map
- `theme_priority_order`
- `hot_theme_token_budget`

Output:
- rendered hot themes
- cold theme name list

Rules:
- render top-down from `theme_priority_order`
- stop when the token budget is exhausted
- if the priority order is invalid, fail loudly

Do not:
- guess missing priority entries
- silently drop unknown theme names
- auto-heal the ordering

## Anchor Update Rules

Theme anchor operations should be explicit.

When updating anchors:
- add missing `ANCHORS` edges
- delete removed `ANCHORS` edges
- validate that all anchor targets exist as `SemanticNode`

Do not store duplicated anchor edges.

## Theme Retirement

Retirement means:
- remove the theme node
- remove its anchor edges
- remove the theme from priority order

If the theme does not exist, fail.

## Acceptance Criteria

- themes can be created, updated, and retired directly
- theme mode can update the map from a delta payload
- hot-theme rendering produces a bounded working set and cold index
- invalid priority order or invalid anchor targets fail loudly
