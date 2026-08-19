"""
network-tool capture addon for mitmproxy.

Loaded via `mitmdump -s capture.py` (or `mitmweb -s capture.py`). Runs inside
mitmproxy's own frozen interpreter, so it imports ONLY the standard library and
`mitmproxy.*` — never third-party packages (there is no pip in the cask build).

Responsibilities:
  1. Append every HTTP response / error / WebSocket message to a greppable
     JSON-Lines file ($NTOOL_HOME/captures/<session>.jsonl) that the `ntool`
     CLI reads back. The binary `.flows` file (written by mitmdump's own `-w`)
     is kept alongside for replay; this JSONL is purely for inspection.
  2. Discover runtime-only hosts (chat WebSocket + CDN bases) from `chat/init`
     responses and record them, because they are never hardcoded in the apps.
  3. Apply request/response overrides from a hot-reloaded rules.json.

Environment (all optional, defaulted):
  NTOOL_HOME     capture home dir              (default: ~/.network-tool)
  NTOOL_SESSION  session name -> <name>.jsonl  (default: "live")
  NTOOL_RULES    overrides file                (default: $NTOOL_HOME/rules.json)
  NTOOL_CLIENT   label stamped on each record  (e.g. "sim:Prismi", "web:Chrome")
  NTOOL_MAX_BODY max stored body chars         (default: 262144)
"""

import asyncio
import json
import logging
import os
import re
import time

from mitmproxy import http

logger = logging.getLogger("ntool.capture")


# MARK: - Configuration

def _home():
    return os.path.expanduser(os.environ.get("NTOOL_HOME", "~/.network-tool"))


def _session_file():
    session = os.environ.get("NTOOL_SESSION", "live")
    directory = os.path.join(_home(), "captures")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{session}.jsonl")


def _rules_file():
    return os.environ.get("NTOOL_RULES", os.path.join(_home(), "rules.json"))


def _discovered_hosts_file():
    return os.path.join(_home(), "discovered-hosts.txt")


def _max_body():
    try:
        return int(os.environ.get("NTOOL_MAX_BODY", "262144"))
    except ValueError:
        return 262144


# MARK: - Body & header extraction

def _headers(message):
    # Preserve duplicate header names (e.g. set-cookie) as ordered pairs.
    return [[name, value] for name, value in message.headers.items(multi=True)]


def _body(message):
    if message is None:
        return None
    content = message.content if message.content is not None else (message.raw_content or b"")
    length = len(content)
    if length == 0:
        return {"len": 0, "text": "", "truncated": False, "binary": False}
    content_type = message.headers.get("content-type", "")
    text = message.get_text(strict=False)
    if text is None:
        return {"len": length, "text": None, "truncated": True, "binary": True,
                "content_type": content_type}
    limit = _max_body()
    truncated = len(text) > limit
    return {"len": length, "text": text[:limit], "truncated": truncated, "binary": False}


def _write_record(record):
    try:
        with open(_session_file(), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        logger.warning("ntool: could not write capture record: %s", error)


def _http_record(flow, kind):
    request = flow.request
    response = flow.response
    duration_ms = None
    if response is not None and response.timestamp_end and request.timestamp_start:
        duration_ms = round((response.timestamp_end - request.timestamp_start) * 1000)
    record = {
        "id": flow.id,
        "ts": time.time(),
        "client": os.environ.get("NTOOL_CLIENT", ""),
        "kind": kind,
        "replay": bool(getattr(flow, "is_replay", None)),
        "method": request.method,
        "scheme": request.scheme,
        "host": request.pretty_host,
        "port": request.port,
        "path": request.path,
        "url": request.pretty_url,
        "req_headers": _headers(request),
        "req_body": _body(request),
        "status": response.status_code if response is not None else None,
        "resp_headers": _headers(response) if response is not None else None,
        "resp_body": _body(response) if response is not None else None,
        "duration_ms": duration_ms,
    }
    if flow.error is not None:
        record["error"] = flow.error.msg
    return record


# MARK: - Runtime host discovery (chat/init)

def _discover_hosts(flow):
    if not flow.request.path.rstrip("/").endswith("/chat/init"):
        return
    if flow.response is None:
        return
    body = flow.response.get_text(strict=False)
    if not body:
        return
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return

    found = set()

    def _collect(value):
        if isinstance(value, str) and re.match(r"^(wss?|https?)://", value):
            match = re.match(r"^[a-z]+://([^/?#]+)", value)
            if match:
                found.add(match.group(1))
        elif isinstance(value, dict):
            for item in value.values():
                _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    _collect(payload)
    if not found:
        return

    path = _discovered_hosts_file()
    existing = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            existing = {line.strip() for line in handle if line.strip()}
    fresh = sorted(found - existing)
    if fresh:
        with open(path, "a", encoding="utf-8") as handle:
            for host in fresh:
                handle.write(host + "\n")
        logger.info("ntool: discovered hosts from chat/init: %s", ", ".join(fresh))


# MARK: - Overrides (hot-reloaded rules.json)

class Rules:
    def __init__(self):
        self._mtime = None
        self._rules = []

    def current(self):
        path = _rules_file()
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            if self._rules:
                logger.info("ntool: rules file gone, clearing overrides")
            self._mtime = None
            self._rules = []
            return self._rules
        if mtime != self._mtime:
            self._mtime = mtime
            try:
                with open(path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
                self._rules = loaded if isinstance(loaded, list) else []
                logger.info("ntool: loaded %d override rule(s)", len(self._rules))
            except (ValueError, OSError) as error:
                logger.warning("ntool: bad rules.json (%s); overrides disabled", error)
                self._rules = []
        return self._rules


_rules = Rules()


def _matches(match, flow):
    request = flow.request
    if "method" in match and request.method.upper() != str(match["method"]).upper():
        return False
    if "host" in match and str(match["host"]).lower() not in request.pretty_host.lower():
        return False
    if "url" in match:
        pattern = str(match["url"])
        if pattern.startswith("~"):
            if not re.search(pattern[1:], request.pretty_url):
                return False
        elif pattern not in request.pretty_url:
            return False
    if "status" in match:
        if flow.response is None or flow.response.status_code != int(match["status"]):
            return False
    return True


def _apply_request_mutation(flow, action):
    request = flow.request
    for name, value in (action.get("headers") or {}).items():
        request.headers[name] = value
    if "set_json" in action:
        try:
            body = json.loads(request.get_text(strict=False) or "{}")
        except (ValueError, TypeError):
            body = {}
        if isinstance(body, dict):
            body.update(action["set_json"])
        request.text = json.dumps(body)
        request.headers["content-type"] = "application/json"
    elif "set_body" in action:
        request.text = str(action["set_body"])


def _make_response(action, default_status):
    status = int(action.get("status", default_status))
    headers = {name: str(value) for name, value in (action.get("headers") or {}).items()}
    if "json" in action:
        headers.setdefault("content-type", "application/json")
        body = json.dumps(action["json"])
    else:
        body = str(action.get("body", ""))
    return http.Response.make(status, body, headers)


# MARK: - Event hooks

async def request(flow: http.HTTPFlow):
    for rule in _rules.current():
        match = rule.get("match", {})
        action = rule.get("action", {})
        kind = action.get("type")
        # status-conditioned rules and mutate_response are evaluated at response time.
        if "status" in match or kind == "mutate_response":
            continue
        if not _matches(match, flow):
            continue
        if kind == "delay":
            await asyncio.sleep(int(action.get("ms", 0)) / 1000)
        elif kind == "kill":
            flow.kill()
        elif kind == "block":
            flow.response = _make_response(action, 500)
        elif kind == "replace_response":
            flow.response = _make_response(action, 200)
        elif kind == "mutate_request":
            _apply_request_mutation(flow, action)
        return  # first matching rule wins


def response(flow: http.HTTPFlow):
    for rule in _rules.current():
        match = rule.get("match", {})
        action = rule.get("action", {})
        if action.get("type") != "mutate_response":
            continue
        if not _matches(match, flow):
            continue
        if "status" in action:
            flow.response.status_code = int(action["status"])
        if "json" in action:
            flow.response.text = json.dumps(action["json"])
            flow.response.headers["content-type"] = "application/json"
        elif "body" in action:
            flow.response.text = str(action["body"])
        for name, value in (action.get("headers") or {}).items():
            flow.response.headers[name] = str(value)
        break

    _discover_hosts(flow)
    _write_record(_http_record(flow, "http"))


def error(flow: http.HTTPFlow):
    _write_record(_http_record(flow, "error"))


def websocket_message(flow: http.HTTPFlow):
    if flow.websocket is None:
        return
    message = flow.websocket.messages[-1]
    record = {
        "id": flow.id,
        "ts": message.timestamp or time.time(),
        "client": os.environ.get("NTOOL_CLIENT", ""),
        "kind": "ws",
        "replay": bool(getattr(flow, "is_replay", None)),
        "from_client": bool(message.from_client),
        "opcode": "TEXT" if message.is_text else "BINARY",
        "host": flow.request.pretty_host,
        "url": flow.request.pretty_url,
        "text": message.text if message.is_text else None,
        "len": len(message.content),
    }
    _write_record(record)
