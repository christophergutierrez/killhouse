# ADR Format

ADRs live in `docs/adr/` and use sequential numbering: `0001-slug.md`, `0002-slug.md`, etc.

Create the `docs/adr/` directory lazily — only when the first ADR is needed.

## Template

```md
# {Short title of the decision}

{1-3 sentences: what's the context, what did we decide, and why.}
```

That's it. An ADR can be a single paragraph. The value is in recording *that* a decision was made and *why* — not in filling out sections.

## Optional frontmatter

An ADR may begin with a `---`-delimited frontmatter block using simple `key: value` lines. This is
optional and soft: a single-paragraph ADR with no frontmatter remains valid. v1 supports simple
`key: value` lines only (no nested YAML, no lists, no quoting).

```md
---
status: accepted
implementation: shipped
load_bearing: true
supersedes: ADR-0003
superseded_by: ADR-0007
---

# {Short title of the decision}

{1-3 sentences: what's the context, what did we decide, and why.}
```

Fields and their default semantics when absent:

- **status** (default `accepted`) — `proposed | accepted | deprecated | superseded`. Missing status
  means the ADR is treated as accepted.
- **implementation** (default `unknown`) — `conceptual | planned | partial | shipped | unknown`.
  Controls how the `VALIDATE` loop routes absent code evidence:
  - `conceptual` — no code evidence is expected; the ADR is a pure design decision.
  - `planned` — absence is an Expected gap, not drift.
  - `partial` — weak or missing evidence routes to Needs input.
  - `shipped` — evidence is expected; absence or contradiction can be blocking when `load_bearing` is true.
  - `unknown` (the default) — absent evidence routes to Needs input, not Drift.
- **load_bearing** (default `unknown`, treated as false for blocking) — `true | false | unknown`.
  Only `shipped` + `load_bearing: true` can make a contradiction or absence blocking in `VALIDATE`.
- **supersedes** — the ADR id this decision replaces (e.g. `ADR-0003`).
- **superseded_by** — the ADR id that replaces this one.

Blocking semantics apply only as input to the `VALIDATE` loop, not as normal ADR authoring overhead.
An ADR without frontmatter is always valid; the defaults exist so old terse ADRs never fail.

## Optional sections

Only include these when they add genuine value. Most ADRs won't need them.

- **Considered Options** — only when the rejected alternatives are worth remembering
- **Consequences** — only when non-obvious downstream effects need to be called out

## Numbering

Scan `docs/adr/` for the highest existing number and increment by one.

## When to offer an ADR

All three of these must be true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If a decision is easy to reverse, skip it — you'll just reverse it. If it's not surprising, nobody will wonder why. If there was no real alternative, there's nothing to record beyond "we did the obvious thing."

### What qualifies

- **Architectural shape.** "We're using a monorepo." "The write model is event-sourced, the read model is projected into Postgres."
- **Integration patterns between contexts.** "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in.** Database, message bus, auth provider, deployment target. Not every library — just the ones that would take a quarter to swap out.
- **Boundary and scope decisions.** "Customer data is owned by the Customer context; other contexts reference it by ID only." The explicit no-s are as valuable as the yes-s.
- **Deliberate deviations from the obvious path.** "We're using manual SQL instead of an ORM because X." Anything where a reasonable reader would assume the opposite. These stop the next engineer from "fixing" something that was deliberate.
- **Constraints not visible in the code.** "We can't use AWS because of compliance requirements." "Response times must be under 200ms because of the partner API contract."
- **Rejected alternatives when the rejection is non-obvious.** If you considered GraphQL and picked REST for subtle reasons, record it — otherwise someone will suggest GraphQL again in six months.
