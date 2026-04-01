# CursorAI ADK Roadmap

### `refresh-doc-index` - Refresh the configured documentation index
Status: todo
Depends on: none
Action: refresh_doc_index
Arguments: {"db_path":"data/doc_pages.db","export_dir":"data/spreadsheets","platforms_path":"config/platforms.json"}
Success criteria:
- The SQLite document database exists and contains at least one indexed platform.
- Per-platform CSV exports are refreshed.
Verification:
- Platform counts can be loaded from the database.
- At least one exported CSV exists in `data/spreadsheets`.

### `export-platform-summary` - Export a machine-readable platform summary
Status: todo
Depends on: refresh-doc-index
Action: export_platform_summary
Arguments: {"db_path":"data/doc_pages.db","output_name":"platform-summary.json"}
Success criteria:
- A JSON summary artifact is written for the currently indexed platforms.
- The artifact includes per-platform document counts.
Verification:
- The artifact exists under `data/adk_artifacts`.
- The artifact contains a non-empty `platforms` array.

### `build-mcp-context` - Build a context snapshot for MCP-related docs
Status: todo
Depends on: export-platform-summary
Action: build_context_snapshot
Arguments: {"db_path":"data/doc_pages.db","limit":12,"output_name":"mcp-context.txt","question":"Which indexed pages are most relevant for MCP workflows?","search":"mcp"}
Success criteria:
- A context snapshot is generated from the current documentation index.
- The snapshot is persisted as an artifact for later agent runs.
Verification:
- The context artifact exists under `data/adk_artifacts`.
- The artifact includes the `Documentation index context:` heading.
