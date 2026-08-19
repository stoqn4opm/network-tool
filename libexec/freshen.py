"""
Swap a fresh auth header onto replayed requests during client-replay.

Runs inside mitmproxy's frozen interpreter alongside `mitmdump -C one.flows`.
Reads NTOOL_FRESH_TOKEN / NTOOL_FRESH_HEADER / NTOOL_FRESH_SCHEME from the
environment. No-ops if no token is provided.
"""

import os

from mitmproxy import http


def request(flow: http.HTTPFlow):
    token = os.environ.get("NTOOL_FRESH_TOKEN")
    if not token:
        return
    header = os.environ.get("NTOOL_FRESH_HEADER", "Authorization")
    scheme = os.environ.get("NTOOL_FRESH_SCHEME", "Bearer ")
    flow.request.headers[header] = (scheme + token) if scheme else token
