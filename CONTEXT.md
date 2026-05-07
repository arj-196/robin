# Robin Context

## Purpose

Robin is the repository of executable abilities that the Robin agent
uses to perform work.

## Glossary

### Ability

The primary unit of capability in this repository. An ability is a discoverable
and directly executable component with its own manifest, runtime, and local
documentation.

### Connector

An ability whose purpose is to integrate Robin with an external system such as
Notion.

### App

An ability that exposes a human-facing interface, such as a dashboard or other
web experience.

### Service

An ability that provides long-running operational behavior for Robin. Services
are grouped separately from connectors and apps even when they share runtimes.

### Chore service

A service ability that executes time-based operational actions on a cron cadence.
It decides which chores are due at runtime and records run state for idempotent
daily behavior.

### Auto-coder service

The service ability that claims coding tasks from Notion, delegates repository
edits to Codex, and completes the git workflow for one task per run.

### Manifest

The lightweight machine-readable metadata for a single ability. It defines basic
identity and execution hints, not a strict lifecycle contract.

### Database page

The canonical term for a record in a Notion database. Historical references to
"item" in this repo map to this term.
