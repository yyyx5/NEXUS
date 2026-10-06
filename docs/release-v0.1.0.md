# Nexus v0.1.0 — First public release / 首次公开发布

Nexus — Personal Memory Infrastructure is an open-source reference implementation
extracted from an actively used personal production system. This release creates
an independent codebase; it includes no personal records or production configuration.

Includes versioned SQLite storage, source/evidence validation, relations and aliases,
task/financial/schedule extensions, dossiers and snapshot manifests, bounded queries,
pending/fallback worker and verified backup logic, plus an OpenClaw adapter.

Both Chinese and English READMEs, architecture/data-model/integration/privacy docs,
MIT License, default-deny configuration, a newly invented trip/expense/journal/
correction/retrieval demo and 20 isolated regression tests are included.

Validation: 20 tests pass; fictional demo integrity passes; local official SDK loading
and two-channel mock registration pass without starting a worker. Working files,
staged blobs, fresh Git history and tag metadata undergo privacy checks before
publication. No real-channel deployment of this edition is claimed.

Limitations: host-specific integration and Chinese heuristics; no standalone LLM
parser, vector engine, UI, encrypted database or complete Archive collector. The
production installation continues independently and is not rewritten by this release.

中文：这是 Nexus 第一次公开发布，来自实际个人生产系统的通用代码抽取。
原始证据、版本修订、关联、检索、持久重试与扩展明细按现有实现保留；所有示例
重新编造。真实数据库、归档、私人身份、凭据、附件与运行配置均不发布。
