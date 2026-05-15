
# IA DEV Agent Runtime Contract

This file defines behavioral instructions for runtime agents in IA DEV.

## Scope

- Applies to all chat orchestrations behind `/ia-dev/chat/`.
- Complements `MEMORY.md`, `POLICIES/*`, `SKILLS/*`, and `TOOLS/*`.
- Does not store user data, business records, or mutable memory.

### Core Behavior

- Keep endpoint compatibility and response contract stability.
- Prefer typed business tools over free-form SQL generation.
- Execute with traceability: include `run_id`, `trace_id`, and policy decisions.
- Use capability routing decisions from `application/routing`.
- Respect policy-first execution for memory writes and governance operations.

### Memory Boundaries

- Session memory: conversational short-term context only.
- User memory: preferences of the authenticated user only.
- Business memory: reusable domain knowledge only.
- Workflow state: operational process state only.
- General learned memory: only via approved proposals.

### Governance Rules

- Never write directly to global/general memory without approval.
- Separate user-specific facts from reusable/global facts.
- Classify memory scope before persistence.
- Emit audit events for propose/approve/reject/apply operations.

### Security Rules

- No secrets in memory values.
- Redact high-risk tokens before persisting.
- Respect sensitivity labels (`low`, `medium`, `high`).

### Observability

- Log capability vs legacy divergence in shadow mode.
- Log memory policy decisions and write outcomes.
- Preserve existing observability events and schema.
