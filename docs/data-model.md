# Storage and revision semantics / 数据模型

The checked-in `schema/schema.sql` is extracted base schema v1. `Nexus` creates
immutability triggers for revision, evidence, relation, aliases, operation, and
three typed-detail tables. The SQL additionally protects source and item identity.
Evidence insertion checks a continuous substring of original source text; offsets
are Python/SQLite character offsets, not UTF-8 byte offsets.

`Core` initializes checksum entries for base schema and two additive migrations:

| Migration | Implementation | Added structures |
|---|---|---|
| 1 | `core.py` / `base.py` | base tables, immutability, quote validation, current FTS |
| 2 | `groups.py:init_groups` | immutable `group_context` plus scope index |
| 3 | `completion.py:init_completion` | immutable `summary_manifest` plus lookup index |

`PRAGMA user_version` remains 1; the `migration` table tracks additive versions.
The public edition has a changed base schema checksum because its default agent
identity is generic. **Do not open an existing production database with this edition.**

An item is a stable identity, not a mutable document. Revision n points to n-1;
head switches only after the new revision, evidence, relations, and details are
inserted. Corrections preserve inherited evidence and add a `corrects` link, with
1..8 evidence links allowed per revision. Long correction chains can hit this
bound; widening it requires a deliberate design/test change, not silent pruning.

Relations and aliases are snapshots of each revision, not global mutable edges.
Current queries join item head and active revisions. Soft deletion adds a deleted
revision and removes the current FTS projection; it does not erase Archive or
source history. `nexus_delete_preview` does not perform physical deletion.

Amounts use integer minor units, scale and currency. Supported scales currently:
CNY/USD/EUR/HKD/GBP=2, JPY=0. Direction and entry class remain separate; a planned
price is not an already-booked expense. Dossier totals sum current members using
Python integers and separate currency, scale, direction, and entry class.

A dossier is a normal record Item with `payload.nexus_group`. Members have
`for_group` relations. Conversation context is channel-scoped, source-bound,
and expires after 24 hours; negated membership takes precedence. Closed dossiers
require explicit reopening. Same-name dossiers need dates, distinct aliases, or IDs.

Summary records have `summary_of` relations and an exact member revision manifest.
They are not financial transactions. The manifest stamp detects changed heads,
including a correction that leaves the member count unchanged.

FTS5 trigram indexes current active title/body. The latest tool search route uses
bounded substring queries with visibility/domain filters, while base `search()`
uses FTS for queries of at least three characters. Neither is semantic retrieval.

Pending intents store context and arguments privately in runtime SQLite. A worker
retries at most 25 due rows per pass, with exponential delay capped at one hour,
a 72-hour / 30-attempt exhaustion policy, and a bounded terminal audit. Successful
intents clear retained request/context fields. `origin_item` maps L0 fallback to
the same item for later structuring; checkpoints prevent redundant transcript scans.
