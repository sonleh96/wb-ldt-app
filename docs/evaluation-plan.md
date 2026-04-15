# Evaluation Plan

This document defines the lightweight evaluation harness for LDT Decision Engine v2.

## Scope

The current suite protects:

- deterministic analytics correctness
- retrieval shape and trace visibility
- evidence bundle completeness
- deterministic ranking consistency
- explanation grounding hooks
- known bad-case regressions

## Test Layers

- `tests/unit/`: fast module and workflow checks
- `tests/e2e/`: end-to-end API acceptance flows
- `tests/evals/`: regression scenarios and benchmark-style fixtures

## Current Regression Fixtures

`tests/evals/fixtures/bad_recommendations.json` currently guards against:

- excluded projects leaking into final selection
- explanation outputs losing evidence references

## Extension Guidance

Add new evaluation cases when:

- a bug escapes a previous test layer
- a retrieval or ranking heuristic changes materially
- prompt versions change and grounding behavior must stay stable

Each new eval fixture should:

- describe the scenario in plain language
- name the expected failure or invariant
- avoid coupling to incidental implementation details

## What Still Requires Human Review

- true semantic retrieval quality
- project-review usefulness and completeness
- prompt quality under live model behavior
- policy decisions around warning vs partial-result handling
