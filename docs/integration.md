# Agent / Archive integration

## Running the reference implementation

The default entry is the isolated fictional demo. It does not read existing host
configurations, databases, or account sessions. `examples/fixture.py` creates a
small transcript SQLite and valid Archive records entirely from invented input.
It is for tests only, not a production ingestion API.

Storage has no network or LLM dependency. Natural-language extraction happens in
the host agent's normal reply/tool round. Without a host model, use explicitly
authored proposals; do not claim autonomous extraction.

## OpenClaw adapter (experimental public integration)

`nexus/index.ts` imports external OpenClaw Plugin SDK. Its manifest and package
metadata are in the same directory. The source production adapter was used with
OpenClaw 2026.9.7. This public edition passed local official SDK loading and fictional two-channel
mock registration, without starting a worker. Live-channel deployment is unverified; verify the installed SDK before enabling it.
No SDK code is vendored. Do not edit or replace a running installation to try it.

1. Create an independent runtime directory **outside the repository**, with `state/`.
2. Copy `config/settings.example.json` to `state/settings.json`, set `agent`,
   `account`, absolute `sourceDB` / `archiveRoot` and verified channel-specific owners.
   Leave unused owners empty. Never infer owner identity from a display name.
3. Provide a compatible read-only host transcript and matching Archive.
4. Set `NEXUS_ROOT` in the host process environment. Optional `NEXUS_PYTHON` chooses
   the Python executable; `NEXUS_ZSTD_LIBRARY` locates system libzstd for compressed events.
5. Initialize once before enabling the worker, using the new root:

```sh
python3 -B nexus/service.py init --root /absolute/path/to/isolated-runtime
python3 -B nexus/service.py verify --root /absolute/path/to/isolated-runtime
```

`init` sets existing transcript-window watermarks so past messages are not
implicitly structured. Without initialization the scan starts at zero. Configure
the host to load only `nexus/` as the plugin source according to its supported
plugin mechanism. Do not register two writers for the same runtime root.

`worker` uses a nonblocking flock, periodic scan and reconciliation, checkpoint
persistence, health metadata and daily verified SQLite backup (latest 30).
The plugin restarts an exited worker after five seconds. `state/PAUSED` pauses scan,
reconciliation and periodic backup. Manual CLI backup uses SQLite backup API and
verification rather than copying a live SQLite file. No network listener is added.

The six tools bind provenance from trusted host context. `service.py call` is a
local trusted maintenance interface, not an untrusted HTTP API. Never expose its
`ctx` payload as model-writable arguments or accept owner flags from callers.

## Required host transcript contract

Binder reads:

- `session_windows(session_id, session_key)`;
- `transcript_events(session_id, seq, event_json, event_zstd, event_utf8_bytes)`;
- `conversations(conversation_id, kind, account_id, channel, native_channel_id,
  native_direct_user_id, peer_id, delivery_target)`.

User events carry original text, event ID, timestamp, trusted owner/sender metadata,
transport channel and conversation identity. Tool calls bind to a persisted
assistant event and its exact parent chain to the user event. Nested tool-search
IDs use an OpenClaw-specific pattern and need compatibility tests after host upgrades.
Group chats, other agents/accounts, strangers, cron/heartbeat/subagent sessions,
ambiguous ancestry and modified originals are rejected. No “latest message” fallback.

## Archive contract

Canonical JSON uses UTF-8, sorted keys and compact separators.

- `source_event_sha256 = SHA256(canonical(original event))`.
- `logical_event_id = SHA256(canonical([agent, session, event ID or sequence]))`.
- `archive_event_id = "ocarc1_" + SHA256(canonical([logical ID, source hash]))`.
- `record_sha256 = SHA256(canonical(record excluding record_sha256))`.
- Record path: `conversations/YYYY/MM/DD/<archive_event_id>.json`, using original UTC date.
- Attachment path: `attachments/objects/<first two hash characters>/<SHA256>`.

See `schema/archive-v1.schema.json` and the fixture producer. Binder checks identities,
full original event equality, record/source hashes, and preserved attachment bytes.
Missing Archive records defer saves rather than inventing evidence. This repo
ships the reader/contract, not a replacement collector daemon.

## Other agents and acceptance

Replace the trusted Binder/transcript adapter while retaining source/evidence
invariants and host-derived context. Base storage APIs are low-level trusted APIs;
callers must establish their own transaction and authorization boundaries.
Current intent/health/time rules and adapter prompts are mainly Chinese; timezone
policy has Asia/Shanghai and UTC+8 assumptions that require review elsewhere.
Legacy XLSX selectors are fixed to specific sheet names/columns; not a general importer.

Before live use, independently verify each channel's private identity, save/query/
correction, original hash, group-chat/stranger denial, pending failure/restart, and
restore into a disposable database. Existing single-person production acceptance
does not prove this extracted edition works with every host/version.
