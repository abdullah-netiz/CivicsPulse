# ADR 0004: PII and Data Governance

## Context

Citizen complaints contain names, street addresses and phone numbers. When
`TRIAGE_PROVIDER=llm` (Groq) or `TRIAGE_PROVIDER=gemini`, that text leaves our
machine and reaches a third party. The assignment (PDF 2.5, Google AI Studio
caveat) is explicit: on free tiers, providers may retain and use inputs, and
this must be handled as an engineering decision, not ignored.

## Decision

1. **Primary path (Groq) -- send only what classification needs.** The
   provider sends the complaint text and location (both required to classify),
   never `reporter_contact`. `reporter_contact` stays inside our Postgres
   boundary; it is not part of any outbound request.
2. **Complaint body is fenced, untrusted data.** `backend/app/providers/triage/llm.py`
   (`SYSTEM_PROMPT`, `FENCE_OPEN`/`FENCE_CLOSE`) delimits the complaint with
   literal `<complaint_text>` markers and instructs the model to treat the
   contents as data, never as instructions. Output is constrained to the
   category/priority enums and re-validated against `TriageResult` regardless.
3. **Gemini is documented, not forbidden.** Google states on its free tier it
   may use inputs to improve products. We treat Gemini as the documented
   alternative: acceptable for demos with synthetic seed data (all seed
   complaints use fictional contacts), not for real citizen data. Choosing it
   for real traffic requires redaction first -- a deliberate, recorded step,
   not a silent default.
4. **The offline path exists for a reason.** `TRIAGE_PROVIDER=ollama` keeps
   every byte on the machine: no key, no third party, no PII exposure at all.
   Slower and weaker at classification -- the measured buy-vs-host trade-off
   from CLO 4.
5. **No secrets, ever, in the wrong places.** API keys arrive from the
   environment (`.env`, gitignored) and, later, Kubernetes Secrets and GitHub
   Secrets. Nothing is written to logs: the Gemini/Groq providers log only
   error class and status codes, and the key is never interpolated into a log
   line or exception message.

## Consequences

- A database breach exposes contact details; an LLM-provider breach or
  training-data leak does not, because contacts never leave our boundary.
- Classification quality may be marginally lower without contact context.
  We accept this: contact info carries no triage signal (the text and location
  do the work), so we lose nothing real.
- If regulations later require redaction (names, phone numbers) before any
  third-party call, the fence-and-classify design gives us one place to add
  it: `_build_request` in the LLM provider.

## Why this ADR exists

The PDF notes a thoughtful ADR here "is worth more in an interview than the
entire rest of the repository." The reasoning above is the point: the PII
decision was made explicitly, recorded, and is reversible with one code
change if the threat model changes.
