# Keeping production and open source independent / 后续同步

Production is authoritative for its own operation. The public edition is an
independent reference implementation, not a deployment target or database mirror.
Do not copy either whole tree onto the other, reuse a production database, or
push a private Git repository/history to this public remote.

1. Finish and verify the production change under the local maintenance rules.
2. Read the public extraction manifest. Compare only exact approved source modules
   against their previous hashes; review source diff locally for embedded identities,
   paths, examples, prompts, logging and credentials.
3. Port the smallest generic change into an open-source branch. Preserve configurable
   identity/root, independent Schema, default-deny owner lists and isolated runtime.
4. Write entirely new fictional regression cases. Never redact real user records
   into fixtures or copy production screenshots/results.
5. Run tests, demo, staged diff review and privacy audit (including an external local
   private-name denylist). Check all reachable Git commits and tag metadata.
6. Update bilingual capability/limit documentation and per-module provenance hashes.
   Mark what is actually verified versus host integration that still needs acceptance.
7. Commit only reviewed exact paths; publish via PR/new release. Keep private deployment
   records locally, in their existing category/index and backup allowlist scope.

There is deliberately no unattended rsync or automatic production-to-public push.
If a leak is suspected, stop publication. Removing a file in a later commit does
not remove it from earlier history; investigate before adding any further commits.
