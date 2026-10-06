# Contributing

Use invented examples, never real conversations or lightly redacted personal records.
Keep runtime data outside the checkout. Do not include private environment exports,
credentials, account identifiers, attachments, or production snapshots in issues or PRs.

Before proposing a change:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/demo.py
python3 -B scripts/privacy_audit.py
```

Explain the behavior change and evidence. Preserve exact evidence spans, immutable
history, transaction boundaries, source authorization, and honest pending receipts.
Test failure/restart and concurrency paths when affected. Do not introduce network
model calls into storage or silently promote inference into fact.

For production-to-public synchronization, use [the extraction workflow](docs/synchronization.md).
Do not copy a runtime directory or production tests wholesale. Contributions are
licensed under MIT; declare external code and its license before including it.
