#!/usr/bin/env python3
"""
Reader/formatter for network-tool capture JSONL.

Runs on the system python3 (3.9+) with the standard library only — it never
imports mitmproxy (the cask ships no runnable interpreter). Backs the
`ntool list | show | export` commands.

By default it MASKS credentials (auth headers, cookies, token-looking body
fields, and query strings) so printed output cannot leak a token into a
context that might be filtered/rejected. Pass --raw to reveal everything.

Usage:
  flow_read.py list   <jsonl> [--filter S] [-n N] [--raw]
  flow_read.py show   <jsonl> <id>          [--raw]
  flow_read.py export <jsonl> [--trim]      [--raw]
"""

import argparse
import json
import re
import sys

SENSITIVE_HEADERS = {
    "authorization", "rm-authentication", "cookie", "set-cookie",
    "x-api-key", "proxy-authorization", "x-auth-token",
}
SENSITIVE_BODY_KEYS = re.compile(
    r'"(accessToken|refreshToken|token|password|secret|apiKey|api_key|authorization)"'
    r'(\s*:\s*)"([^"]*)"',
    re.IGNORECASE,
)


# MARK: - Masking

def mask_value(value):
    return f"<masked:len={len(value or '')}>"


def mask_header(name, value):
    if name.lower() in SENSITIVE_HEADERS:
        return mask_value(value)
    return value


def mask_url(url):
    if "?" not in url:
        return url
    base, query = url.split("?", 1)
    count = len([p for p in query.split("&") if p])
    return f"{base}?<qs:{count} param{'s' if count != 1 else ''}>"


def mask_path(path):
    if "?" not in path:
        return path
    base = path.split("?", 1)[0]
    return base + "?…"


def mask_body_text(text):
    if not text:
        return text
    return SENSITIVE_BODY_KEYS.sub(lambda m: f'"{m.group(1)}"{m.group(2)}"{mask_value(m.group(3))}"', text)


# MARK: - Loading

def load(jsonl_path):
    records = []
    try:
        with open(jsonl_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return records


def short_id(flow_id):
    return (flow_id or "").replace("-", "")[:8]


# MARK: - Rendering

def pretty_body(body, raw):
    if not body:
        return "(none)"
    if body.get("binary"):
        return f"<binary {body.get('len', 0)} bytes {body.get('content_type', '')}>".strip()
    text = body.get("text") or ""
    if not raw:
        text = mask_body_text(text)
    try:
        text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except ValueError:
        pass
    if body.get("truncated"):
        text += f"\n… (truncated, full length {body.get('len', 0)})"
    return text


def render_headers(headers, raw):
    if not headers:
        return "  (none)"
    lines = []
    for name, value in headers:
        shown = value if raw else mask_header(name, value)
        lines.append(f"  {name}: {shown}")
    return "\n".join(lines)


def cmd_list(records, args):
    if args.filter:
        needle = args.filter.lower()
        records = [r for r in records
                   if needle in (r.get("url", "") + r.get("method", "") + r.get("host", "")).lower()]
    if args.n:
        records = records[-args.n:]
    for record in records:
        kind = record.get("kind")
        if kind == "ws":
            arrow = "→" if record.get("from_client") else "←"
            preview = (record.get("text") or f"<{record.get('opcode')}>")[:60].replace("\n", " ")
            print(f"{short_id(record['id'])}  WS {arrow}  {record.get('host', '')}  {preview}")
        else:
            status = record.get("status")
            status = str(status) if status is not None else ("ERR" if kind == "error" else "-")
            path = record.get("path", "")
            path = path if args.raw else mask_path(path)
            print(f"{short_id(record['id'])}  {record.get('method', ''):6} {status:>3}  "
                  f"{record.get('host', '')}  {path}")


def cmd_show(records, args):
    matches = [r for r in records if (r.get("id") or "").startswith(args.id)
               or short_id(r.get("id")) == args.id or short_id(r.get("id")).startswith(args.id)]
    if not matches:
        print(f"no flow matching id '{args.id}'", file=sys.stderr)
        return 1
    for record in matches:
        _show_one(record, args.raw)
    return 0


def _show_one(record, raw):
    print("=" * 70)
    if record.get("kind") == "ws":
        arrow = "client → server" if record.get("from_client") else "server → client"
        print(f"WebSocket message ({arrow})  id={record.get('id')}")
        print(f"host: {record.get('host')}")
        print(f"opcode: {record.get('opcode')}  len: {record.get('len')}")
        text = record.get("text")
        if text is not None:
            print("\n" + (text if raw else mask_body_text(text)))
        return
    url = record.get("url", "")
    print(f"{record.get('method', '')} {url if raw else mask_url(url)}")
    print(f"id: {record.get('id')}   client: {record.get('client', '')}   "
          f"replay: {record.get('replay')}   duration_ms: {record.get('duration_ms')}")
    if record.get("error"):
        print(f"error: {record['error']}")
    print("\n--- request headers ---")
    print(render_headers(record.get("req_headers"), raw))
    print("\n--- request body ---")
    print(pretty_body(record.get("req_body"), raw))
    status = record.get("status")
    print(f"\n--- response ({status if status is not None else '-'}) headers ---")
    print(render_headers(record.get("resp_headers"), raw))
    print("\n--- response body ---")
    print(pretty_body(record.get("resp_body"), raw))


def cmd_export(records, args):
    if not args.trim:
        for record in records:
            if not args.raw:
                record = _mask_record(record)
            print(json.dumps(record, ensure_ascii=False))
        return 0
    for record in records:
        if record.get("kind") == "ws":
            arrow = "→" if record.get("from_client") else "←"
            preview = (record.get("text") or f"<{record.get('opcode')}>")[:80].replace("\n", " ")
            print(f"WS {arrow} {record.get('host', '')}  {preview}")
            continue
        url = record.get("url", "")
        status = record.get("status")
        status = str(status) if status is not None else "-"
        line = f"{record.get('method', ''):6} {status:>3}  {url if args.raw else mask_url(url)}"
        resp = record.get("resp_body") or {}
        excerpt = (resp.get("text") or "")[:160].replace("\n", " ")
        if excerpt:
            excerpt = excerpt if args.raw else mask_body_text(excerpt)
            line += f"\n            ↳ {excerpt}"
        print(line)
    return 0


def _mask_record(record):
    clone = dict(record)
    if clone.get("req_headers"):
        clone["req_headers"] = [[n, mask_header(n, v)] for n, v in clone["req_headers"]]
    if clone.get("resp_headers"):
        clone["resp_headers"] = [[n, mask_header(n, v)] for n, v in clone["resp_headers"]]
    if clone.get("url"):
        clone["url"] = mask_url(clone["url"])
    for key in ("req_body", "resp_body"):
        body = clone.get(key)
        if body and body.get("text"):
            body = dict(body)
            body["text"] = mask_body_text(body["text"])
            clone[key] = body
    return clone


# MARK: - Entry

def main(argv):
    parser = argparse.ArgumentParser(prog="flow_read.py")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("jsonl")
    p_list.add_argument("--filter", default=None)
    p_list.add_argument("-n", type=int, default=None)
    p_list.add_argument("--raw", action="store_true")

    p_show = sub.add_parser("show")
    p_show.add_argument("jsonl")
    p_show.add_argument("id")
    p_show.add_argument("--raw", action="store_true")

    p_export = sub.add_parser("export")
    p_export.add_argument("jsonl")
    p_export.add_argument("--trim", action="store_true")
    p_export.add_argument("--raw", action="store_true")

    args = parser.parse_args(argv)
    records = load(args.jsonl)
    if args.command == "list":
        return cmd_list(records, args) or 0
    if args.command == "show":
        return cmd_show(records, args)
    if args.command == "export":
        return cmd_export(records, args)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
