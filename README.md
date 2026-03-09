# CursorAI Docs Database

`CursorAI` now contains a small documentation database toolkit for indexing `llms.txt`
files from LLM and agent platforms, exporting them into per-platform spreadsheets,
filtering them for AI workflows, and browsing them through a local web UI.

## What it does

- Ingests platform `llms.txt` indexes into a local SQLite database
- Exports one CSV spreadsheet per platform under `data/spreadsheets/`
- Lets you query/filter docs by platform, section, text, and markdown-only mode
- Builds compact context blocks that can be handed to LLMs and agents
- Optionally sends filtered context to OpenAI with `OPENAI_API_KEY`
- Serves a local browser UI for interactive browsing and ad hoc questions

## Included platforms

- OpenAI
- Twin
- LangChain
- Onyx
- Statsig
- StackAI

The platform list lives in `config/platforms.json`, so adding more providers is just
adding another entry and re-running ingest.

## Quickstart

Create the database and refresh the CSV spreadsheets:

```powershell
$env:PYTHONPATH = "src"
python -m docdb.cli ingest --db data/doc_pages.db --platforms config/platforms.json --export-dir data/spreadsheets
```

Browse the docs locally:

```powershell
$env:PYTHONPATH = "src"
python -m docdb.cli serve --db data/doc_pages.db --host 127.0.0.1 --port 8765
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

## Useful commands

Export spreadsheets directly from the platform config:

```powershell
$env:PYTHONPATH = "src"
python -m docdb.cli seed-spreadsheets --platforms config/platforms.json --out data/spreadsheets
```

Query the indexed docs:

```powershell
$env:PYTHONPATH = "src"
python -m docdb.cli query --db data/doc_pages.db --platform openai --search mcp --markdown-only --limit 20
```

Build LLM-ready context from filtered docs:

```powershell
$env:PYTHONPATH = "src"
python -m docdb.cli context --db data/doc_pages.db --platform langchain --search agent --limit 15
```

Ask OpenAI with the selected context:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:PYTHONPATH = "src"
python -m docdb.cli ask --db data/doc_pages.db --platform openai --search tools --question "Which pages look most relevant for MCP tool building?"
```

## Config format

`config/platforms.json` is the canonical source for platform definitions:

```json
{
  "schema": "cursorai-docdb-platforms-v1",
  "platforms": [
    {
      "id": "openai",
      "name": "OpenAI",
      "llms_url": "https://developers.openai.com/llms.txt",
      "homepage": "https://developers.openai.com/"
    }
  ]
}
```

## Data model

Each indexed document stores:

- `platform_id`
- `title`
- `url`
- `rel_path`
- `section`
- `description`
- `content_type`
- `is_markdown`

This keeps the database compact while still being useful for routing, filtering,
RAG pre-selection, and spreadsheet exports.

## Notes

- The SQLite database file is intentionally ignored in git.
- The CSV spreadsheets are committed because they are easy to inspect and useful as a
  ready-made docs inventory snapshot.
- The OpenAI integration is optional and only used when `OPENAI_API_KEY` is set.

