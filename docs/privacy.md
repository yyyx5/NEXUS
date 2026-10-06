# Privacy and release audit

Privacy takes precedence over publication. This edition was built in a new directory
using an explicit source-file allowlist. No data, state, config instance, backup,
log, attachment or private test directory was recursively copied. All demo fixtures
are newly authored from invented text, dates, amounts, IDs and metadata.

Pre-publication checks include working files, exact staged blobs, full reachable
Git history and commit/tag identity. The scanner checks machine home paths, phone,
email and bank-like number patterns, credential formats and suspicious secret
assignments, prohibited binary/runtime suffixes and runtime directories. A private
external denylist adds known personal names, machine username, real trip identifiers
and identity metadata without putting those values into this repository.

`.gitignore` is a guard, not a privacy proof. Ignored files can still be force-added;
scans and manual staged review remain necessary. Findings report filename/rule,
not matched private content. No scanner can prove the absence of every indirect
identifier. Review all newly changed files before every public push.

## v0.1.0 acceptance

- Independent extraction: 16 Nexus files plus a data-only Archive JSON contract.
- Runtime settings replaced by a default-deny example with fictional identity.
- New fictional fixtures and 20 meaningful tests pass in disposable directories.
- Demo checks source binding, shared-channel save/query, revision history,
  correction evidence, `for_group`, current totals and stale summaries.
- Production code is hash-compared before/after; no production records are written.
- The full OpenClaw adapter is included as experimental integration; no new live
  deployment or real-channel acceptance is claimed for the public edition.
- The release file inventory, staged content and fresh repository history are audited
  before creating the public remote. Tags use public author metadata.

## Known security boundaries

This is trusted single-person local infrastructure. Host owner metadata and private
filesystem ownership are trusted. SQLite is not encrypted; triggers/hashes do not
protect against the owner rewriting the database and recalculating hashes. There
is no hostile multi-tenant authorization layer or encrypted attachment store.

Intent, health gating, dates and negation include Chinese heuristics. Pending
reconciliation uses stored trusted context, but health-access state on a long-lived
worker needs additional dedicated review before relying on asynchronous health
corrections. Keyword gating is not a complete data-loss-prevention classifier.

Archive history scans a trusted corpus; malformed or very large inputs can cause
errors or high resource use. Restricted filtering is not a substitute for OS-level
access control. Low-level storage and CLI context are trusted APIs, not public
network endpoints. Use independent integration/security acceptance before deployment.

Backups remain private runtime artifacts and include sensitive data. Git is not a
backup mechanism for personal memory. Keep restoration procedures and access
controls separate from source-code publication.
