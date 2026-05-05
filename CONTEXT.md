# Hermes Tools Context

## Purpose

Hermes Tools is the repository of executable abilities that the Hermes agent
uses to perform work.

## Glossary

### Ability

The primary unit of capability in this repository. An ability is a discoverable
and invokable component with its own manifest, runtime, and lifecycle commands.

### Connector

An ability whose purpose is to integrate Hermes with an external system such as
Notion.

### App

An ability that exposes a human-facing interface, such as a dashboard or other
web experience.

### Service

An ability that provides long-running operational behavior for Hermes. Services
are grouped separately from connectors and apps even when they share runtimes.

### Registry

The repo-level index that tells Hermes which abilities are discoverable and
where their manifests live.

### Manifest

The machine-readable contract for a single ability. It defines identity, type,
runtime, environment requirements, and lifecycle commands.

### Database page

The canonical term for a record in a Notion database. Historical references to
"item" in this repo map to this term.
