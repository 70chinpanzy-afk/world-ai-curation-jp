# Source Strategy

## Priority Rules
- Tier A (Primary): global official and first-party sources
- Tier B (Trusted reporting): high-quality international media
- Tier C (Signals): community/social sources (X, note)

## Tier A Examples
- arXiv (AI categories)
- OpenAI, Anthropic, Google DeepMind, Meta AI official blogs/docs
- major OSS repos and release notes
- benchmark/standards announcements

## Tier B Examples
- Reuters tech, Financial Times tech, The Information
- MIT Technology Review, IEEE Spectrum (AI coverage)
- specialized AI newsletters with clear sourcing

## Tier C Examples
- X posts from verified researchers/builders
- note posts (mainly Japanese explainers)

## Weighting Policy
- Tier A: highest trust and ranking weight
- Tier B: medium trust
- Tier C: low trust by default, used as context or lead

## X and note Policy
- X and note are optional add-ons, not headline drivers
- Tier Cの収集件数は1ソースごとに上限をかける（デフォルト4件）
- If a story exists only on X/note and has no corroboration:
  - keep in "signals" section
  - avoid strong claims
- Promote to main feed only after confirmation from Tier A/B

## De-duplication Policy
- 同一URLは1件に統合
- 近い見出し（同一ストーリー）は1件に統合
- 統合時は Tier の高いソースを優先し、同Tierなら新しさと実装可能性を優先

## Language Policy
- Preserve source language snippets
- Provide Japanese translation for accessibility
- Distinguish clearly:
  - direct facts from sources
  - inferred interpretation
