# ADR 0004: Gemini PII and Data Governance

## Decision

CivicPulse sends the complaint text and location to Gemini only when `TRIAGE_PROVIDER=gemini`. Reporter contact details are never included in the Gemini request. The request is sent over HTTPS using `GEMINI_API_KEY` from the backend environment; the key is never included in frontend code, logs, or committed files.

The application treats complaint text as untrusted data. It is delimited in the request, Gemini is constrained to the category and priority enums, and the response is validated with `TriageResult` before persistence. A timeout, retry exhaustion, provider error, or invalid response uses the local rule-based fallback so citizen submission does not depend on Gemini availability.

## Rationale and risk

Location can identify a public incident and complaint text may contain names or phone numbers supplied by citizens. Excluding reporter contact reduces exposure. The team accepts sending complaint text and location to Google's API for this assignment's triage demonstration, with the provider configuration documented and replaceable. A production deployment would add explicit retention/vendor review, redaction of direct identifiers, and a consent/privacy notice before enabling hosted triage.

## Consequences

Gemini improves classification quality but introduces vendor, network, quota, and data-governance risk. The provider interface, Redis content cache, 10-second timeout, one retry, validation, and rule fallback keep the rest of the system operational when the vendor is slow or unavailable.
