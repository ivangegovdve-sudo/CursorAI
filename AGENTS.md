# AGENTS.md - CursorAI Working Guide

This repository is reserved for Cursor-related workflows, experiments, and operational tooling. At the moment it appears unused, so treat it as a placeholder with intent, not as an active product.

## Goal

- provide a dedicated repo for Cursor-specific experiments or utilities
- keep any future work anchored to practical personal workflows
- avoid building a product until a repeatable need exists

## Current Idea And Progress

- Intended purpose:
  a workspace tied to Cursor usage or Cursor-adjacent tooling
- Current state:
  nearly empty and not clearly in use
- Progress level:
  concept only

## Initial Setup Requirements

- do not introduce a full stack until a concrete use case is chosen
- start with:
  a real `README.md`
  a simple folder structure
  `.env.example` if external APIs are needed
- preferred first implementation:
  small scripts, templates, or local utilities

## Environments

- local development only for now
- no defined staging or production environments

## Dependencies

- none required yet
- possible future dependencies:
  local config parsers, usage trackers, model metadata, note indexing, or account summaries

## Backend Need

- backend required now:
  no
- backend likely later:
  optional, only if usage history, reminders, or dashboards become useful
- likely backend shape:
  a small local API with SQLite if this grows beyond scripts and markdown

## Development Plan

1. Decide what this repo is actually for.
   Good candidates: Cursor setup templates, workflow automation, usage tracking, instruction libraries, or research logs.
2. Build the smallest useful artifact first.
3. Keep the repo private and operational if it mainly stores personal workflow intelligence.
4. Add a backend only after the data or automation needs justify it.
5. Archive or repurpose the repo if the use case never becomes concrete.

## End Goal

The end goal is either:
- a lean operational repo for useful Cursor workflows
or
- a consciously retired placeholder if no strong use case materializes

Do not let it drift into a vague miscellaneous bucket.
