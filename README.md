# network-tool (`ntool`)

A small, CLI-first wrapper around **[mitmproxy](https://mitmproxy.org)** for capturing, inspecting, overriding, and replaying the HTTP(S) and WebSocket traffic of iOS-simulator apps **and** web apps — from the terminal, so an agent (or you) can drive it without a GUI.

It is **not a proxy of its own**. mitmproxy already does TLS interception, capture, intercept/modify, replay, WebSocket, and save/load. `ntool` adds only the parts mitmproxy leaves to you: a greppable capture log, a query/inspect CLI, a declarative override file, replay with fresh tokens, and named sessions.

## Why

- **See what an app is actually sending** — headers, bodies, params, tokens.
- **Verify your work** — capture the wire traffic before/after a change and diff it.
- **Explore an API** — capture, then replay and mutate requests.
- **Web → iOS** — capture a feature's real traffic in the web app (the reference client), then recreate it in the iOS services and diff for parity.

## Install

mitmproxy ships as a Homebrew **cask** (a formula can't auto-install it), and Homebrew 6.0 requires trusting third-party taps, so install is a few steps:

```bash
brew install --cask mitmproxy
brew tap stoqn4opm/tap https://github.com/stoqn4opm/network-tool.git
brew trust stoqn4opm/tap          # Homebrew 6.0 requires trusting third-party taps
brew install network-tool
ntool setup
```

(The repo doubles as its own Homebrew tap — the `Formula/` directory lives in it, so no separate `homebrew-tap` repo is needed.)

Or without Homebrew (single machine / dev):

```bash
git clone https://github.com/stoqn4opm/network-tool.git
cd network-tool && ./install.sh          # symlinks `ntool` onto your PATH
brew install --cask mitmproxy
ntool setup
```

## Setup

```bash
ntool setup              # trusts the mitmproxy CA in the booted simulator AND system-wide (Safari/Chrome)
ntool setup --sim        # simulator only (no sudo)
ntool setup --browser    # system-wide only (one sudo prompt)
ntool doctor             # environment / status check
```

The first `--mode local` capture asks macOS to approve mitmproxy's network extension once (**System Settings ▸ Network ▸ Filters**) — approve it.

## Capture

```bash
ntool capture on --sim Prismi          # capture just the simulator app (no sudo)
ntool capture on --web "Google Chrome" # capture just a browser process
ntool capture on --proxy               # route the whole system (sim + real browser) via mitmproxy
ntool capture on --sim Prismi --headless "~m (POST|PUT)"   # no live UI, filtered to POST/PUT
ntool capture off                      # stop (restores prior proxy settings if --proxy was used)
```

- **Routing.** `--sim`/`--web` use mitmproxy's `local` mode (scoped to one process, **no sudo**). `--proxy` sets the macOS system proxy (needs your password; **restart the Simulator** afterwards) and captures everything at once.
- **Live view.** By default capture runs the `mitmweb` front-end — open **http://127.0.0.1:8081** to watch traffic in a Charles-like browser UI while it records. `--headless` skips the UI.
- **Filter.** Any trailing argument is a [mitmproxy filter](https://docs.mitmproxy.org/stable/concepts/filters/) limiting what's saved, e.g. `"~d ts4date\.com"`, `"~m POST"`, `"!~a"` (no assets).

## Inspect

```bash
ntool list                       # recent flows: id  method  status  host  path
ntool list --filter chat -n 20   # filter + last 20
ntool show <id>                  # full request/response (tokens MASKED)
ntool show <id> --raw            # reveal tokens/bodies verbatim
ntool hosts                      # wss/CDN hosts discovered from chat/init responses
```

Credentials (auth headers, cookies, `accessToken`/`password`-style body fields, query strings) are **masked by default**; `--raw` reveals them.

## Override (breakpoint / modify)

Overrides live in a JSON file that the capture process **hot-reloads** — no restart. See [`examples/rules.json`](examples/rules.json).

```bash
ntool rules set '[{"match":{"url":"/config"},"action":{"type":"replace_response","status":200,"json":{"isMoodsFeatureEnabled":"1"}}}]'
ntool rules show
ntool rules clear
```

Actions: `mutate_request` (`headers`, `set_json`, `set_body`), `replace_response` (fakes a response, server never contacted), `mutate_response` (tweak the real response — use with a `status` in `match`), `block` (force a status), `kill` (drop), `delay` (`ms`). Match on `method`, `url` (substring, or `~regex`), `host`, `status`. First matching rule wins.

## Replay

```bash
ntool replay <id>                # re-fire a captured HTTP request through client-replay
ntool replay <id> --fresh-token  # swap in the current token from the booted sim (defeats stale-auth 401s)
```

WebSocket flows can't be replayed (mitmproxy limitation) — `ntool` refuses them with a clear message. Replayed results land in the `replay` session (`ntool show <id> --session replay`).

## Sessions

```bash
ntool session save probe1              # snapshot the live capture (.jsonl + .flows)
ntool session list
ntool session load probe1              # restore it as the live capture
ntool session export probe1 --trim     # compact digest for reading into context
ntool session export probe1 --har      # HAR file you can open in Charles
ntool view probe1                      # browse a saved capture in the mitmweb UI (read-only)
```

## How it works

- A mitmproxy addon (`capture.py`, runs inside mitmproxy's bundled interpreter) writes each flow to a greppable JSONL under `~/.network-tool/captures/`, discovers runtime-only hosts from `chat/init`, and applies the override rules. mitmproxy's own `-w` writes the binary `.flows` alongside for replay.
- The reader (`flow_read.py`, system `python3`, stdlib only) formats and masks that JSONL for `list`/`show`/`export`.
- Everything you capture stays local under `~/.network-tool/` (git-ignored; never committed).

## Requirements

- macOS, Homebrew, Xcode command-line tools (`xcrun simctl`) for simulator capture.
- mitmproxy (cask). The addon needs no extra Python packages; the reader uses only the system `python3`.

## Versioning

Semantic Versioning (`MAJOR.MINOR.PATCH`). While on `0.x`, the CLI surface may still change. See [`CHANGELOG.md`](CHANGELOG.md).

## License

MIT.
