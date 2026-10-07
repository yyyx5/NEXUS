# Optional Obsidian reading mirror for life memories

[中文](obsidian.md) · Experimental reference implementation · Disabled by default

Nexus works independently as a life memory recorder. This extension creates a Markdown Vault for direct reading in Obsidian. Skipping it does not affect Nexus storage, queries, provenance, or revisions.

## Choose now or enable later

From the repository root:

```sh
python3 -B scripts/obsidian.py setup --language en
```

The program explains purpose, direction, privacy, and limitations before asking. Enter defaults to skipping: no settings, Vault, or scheduled task is created. Rerun the same command whenever you change your mind; no Nexus reinstall is needed.

If enabled, provide your own Nexus SQLite path and a local folder named `Nexus`. Health/restricted records and unfinished intents are excluded unless separately enabled. iCloud is also off by default; choosing it sends the selected material to Apple's sync service.

Real settings are external to the repository; the program displays their location. Use `--config` to choose another external settings file. `config/obsidian.example.json` is a disabled template, not a working personal configuration. Skipping a later setup leaves existing settings unchanged; use disable to pause.

## Sync, pause, and return

```sh
python3 -B scripts/obsidian.py sync
python3 -B scripts/obsidian.py status
python3 -B scripts/obsidian.py disable
# Enable again or change settings:
python3 -B scripts/obsidian.py setup --language en
```

For custom settings, pass the same `--config <settings-path>` to every command. disable preserves the database, notes, and existing schedule; later sync runs skip. Setup can re-enable it. Changing destinations does not automatically remove old copies.

After understanding the choices, explicitly opt in without prompts; unspecified optional choices stay off:

```sh
python3 -B scripts/obsidian.py setup --language en --enable \
  --database '<absolute-path-to-your-Nexus-database>' \
  --local-vault '<absolute-path-to-local-Nexus>' \
  --timezone UTC
```

`--include-sensitive` explicitly includes sensitive material. `--icloud-vault` explicitly selects a cloud copy. Core Nexus deployment never invokes this script or silently enables it.

## What it presents

- Readable titles and explicit dates; event and recording dates stay separate, ambiguity is not guessed.
- One folder per existing dossier: home, continuous full reading page, and detail notes.
- Category entries, timeline, unclassified index, and synchronization status.
- Readable money/task/schedule fields with expandable evidence and item identifiers.

Title similarity is insufficient for grouping. Unclassified counts cover only records allowed by the selected export scope; unfinished intents without finalized visibility are not expanded by default. Reading templates currently use Chinese.

```text
Nexus → local staging and validation → local Nexus → optional iCloud Nexus
```

Nexus is the sole source of truth; the mirror never writes back. Obsidian is a reading interface, not another database. Edits to generated notes are overwritten on later syncs; corrections and classification belong in Nexus. Full dossier pages concatenate existing records rather than using AI to author essays or new facts. Historical summary snapshots are labeled.

## iCloud and scheduling

`sync --local-only` performs local generation only. Normal sync publishes locally first, then copies to the optional cloud destination. Cloud failures preserve local success. Python standard-library synchronization uses zero model tokens, with no model or cloud API calls.

On macOS, setup uses only an actually existing Obsidian iCloud container. If none is detected, supply a personally verified path. Both Vault directories must be named `Nexus`, separate and non-nested. Install Obsidian yourself; no plugin installation is required.

Optionally generate a daily 04:00 macOS launchd job:

```sh
python3 -B scripts/obsidian.py schedule
# Load only when desired; alternatively inspect and load the plist yourself.
python3 -B scripts/obsidian.py schedule --load
```

04:00 follows the macOS system timezone; the configured timezone controls note display only. An existing, different job is not replaced. Validate loading, background execution, and privacy permissions on your own machine: actual deployment has encountered Python being denied iCloud access by macOS privacy controls. A loaded job does not prove successful automation, and local container writes do not prove mobile delivery.

Linux can use the local mirror with its own scheduler. Windows locking/deployment is currently unsupported. Universal iCloud or mobile installation is not promised.

## Data boundaries and validation

The exporter uses read-only SQLite and a consistent read transaction. Mirrors are unencrypted. OS permissions control direct database access; this exporter does not reuse Agent conversation authorization. Use only your own database, not a shared multi-user service. Health filtering follows existing fields and cannot guarantee every text fragment is free of sensitive information; review the scope before enabling cloud copies.

Cleanup covers only manifest-owned files bearing the generated marker. `.obsidian/` and other files stay; unowned collisions are rejected. Per-file atomic replacement is not a filesystem transaction for the entire Vault. Avoid concurrent manual edits to generated notes. Keep settings, Vaults, logs, and state outside the source repository; do not upload private mirrors.

Public validation uses entirely fictional data for skip/revisit/pause, grouping, amount correction, rename/deletion, user-file preservation, cloud failure with local success, locking, and sensitive opt-in. Long-term cross-device usage remains unverified.

```sh
python3 -B scripts/obsidian_demo.py
# To open the fictional demo, choose a new directory outside the repository.
python3 -B scripts/obsidian_demo.py --output '<new-fictional-demo-directory>'
```

An AI assistant of your choice can follow these instructions and help confirm paths or run deployment commands. Do not upload databases, memories, or credentials to GitHub; what you provide to a cloud AI is a separate choice. AI assistance is outside this extension's core.
