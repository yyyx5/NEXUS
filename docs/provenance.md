# Extraction provenance and license boundary

Audit date: 2026-10-06. Public release: v0.1.0.

The source was an actively running local Nexus service: a Python SQLite core,
OpenClaw TypeScript plugin and tool definitions. Read-only inspection confirmed
the real schema, additive migrations, owner channel configuration, worker heartbeat,
zero pending intents, SQLite quick check and foreign keys. No user record body or
production database was copied into this repository.

`extraction-manifest.json` records module content hashes from the inspected source
and edition output at extraction time. Source locations and machine usernames
are intentionally omitted. It supports local comparisons, not an independently
verifiable public attestation of private production behavior.

The included modules are the existing implementation, with minimal edition changes:

- hardcoded agent/account identities become required settings;
- absolute personal root becomes required `NEXUS_ROOT`;
- schema is separated from code with updated paths and a generic default agent;
- Python executable / system zstd lookup become configurable;
- examples, tests, READMEs and public maintenance documentation are newly written.

Public functional tests are new fictional tests, not copied production fixtures.
The full Archive collector and private migration/acceptance scripts are excluded.
The Archive JSON schema is a data contract extracted without instance data.

The selected Nexus source has no third-party license headers, bundled dependencies,
or vendored third-party implementation. It uses Python/SQLite system APIs and imports
OpenClaw Plugin SDK and system libzstd as external dependencies. The ctypes decoder
is a local wrapper, not copied libzstd code. No conflicting license was identified
in the selected files. This is a source inspection conclusion, not a legal guarantee.

The surrounding private Archive documentation mentions an external format reference;
its documentation/code is not copied here. The reference implementation is licensed
under MIT; downstream integration must comply with external dependencies' own licenses.

The public author/copyright identity is “Nexus contributors”. Git commits use the
repository owner's GitHub no-reply address, not a private email or local machine name.

## Optional Obsidian extension (2026-10-07)

The reading renderer is adapted from the existing local mirror, with generic paths,
configurable display timezone and explicit sensitive-content filtering. The public
local-first synchronizer, opt-in/pause/schedule CLI, fictional demo, tests and bilingual
instructions are newly authored for the edition. No production configuration, LaunchAgent,
database, generated note, attachment, log or personal dossier is included.

The extraction manifest separately records renderer/source hashes and newly authored
modules. The Nexus core and v0.1.0 tag remain unchanged; this extension is experimental.

## v0.2.0 release (2026-10-07)

The optional Obsidian mirror is packaged as the second public release. README
headers, package metadata and the public manifest identify v0.2.0. The manifest
retains the original extraction date/version and source hashes; its package edition
hash reflects the metadata version bump. The v0.1.0 tag and release remain available.
Nexus storage, schema and tool implementations are unchanged.
