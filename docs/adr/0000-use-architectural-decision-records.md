# ADR 0000: Use Architectural Decision Records

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

As the Voysix project grows, it becomes harder to remember why certain architectural choices were made (e.g., why FastAPI for the worker, why Tailscale for networking). We need a way to document these decisions for future maintainers.

## Decision Drivers

* Need for technical clarity.
* Onboarding efficiency for new contributors.
* Long-term maintainability.

## Considered Options

1. Documenting in README.md.
2. Using ADRs in `docs/adr/`.
3. No formal documentation (tribal knowledge).

## Decision Outcome

Chosen option: **ADRs in `docs/adr/`**, because it provides a structured, version-controlled history of the project's evolution without cluttering the main README.

### Consequences

* Good: Clear "paper trail" of architectural evolution.
* Good: Reduces redundant discussions.
* Bad: Requires discipline to keep records updated.
