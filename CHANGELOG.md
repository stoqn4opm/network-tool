# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-19

### Added
- `ntool capture on|off` — capture iOS-simulator or browser traffic via mitmproxy,
  with `--sim`/`--web` (process-scoped `local` mode, no sudo) or `--proxy`
  (system-wide). Live `mitmweb` UI by default; `--headless` for none.
- `ntool list` / `ntool show` — inspect captured flows, with credential masking by
  default and a `--raw` bypass.
- `ntool rules set|show|clear|edit` — hot-reloaded, declarative request/response
  overrides (`mutate_request`, `replace_response`, `mutate_response`, `block`,
  `kill`, `delay`).
- `ntool replay <id>` — client-replay a captured HTTP request, with `--fresh-token`
  to inject the current simulator auth token.
- `ntool session save|load|list|export` — named snapshots; `--trim` digest and
  `--har` (Charles-compatible) export.
- `ntool view` — browse a saved capture in the mitmweb UI read-only.
- `ntool hosts` — surface wss/CDN hosts discovered from `chat/init` responses.
- `ntool setup` / `ntool doctor` — CA trust (simulator + system-wide) and status.
- Homebrew formula and a no-Homebrew `install.sh`.
