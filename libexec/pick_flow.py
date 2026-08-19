"""
Extract a single flow (by id) from a .flows file into a new .flows file.

Runs inside mitmproxy's frozen interpreter: `mitmdump -q -n -s pick_flow.py`.
Reads NTOOL_IN / NTOOL_OUT / NTOOL_PICK from the environment, then shuts down.
WebSocket flows are refused (mitmproxy cannot client-replay them).
"""

import logging
import os

from mitmproxy import ctx, http, io


def running():
    in_path = os.environ["NTOOL_IN"]
    out_path = os.environ["NTOOL_OUT"]
    pick = os.environ["NTOOL_PICK"]
    written = 0
    with open(in_path, "rb") as source, open(out_path, "wb") as target:
        writer = io.FlowWriter(target)
        for flow in io.FlowReader(source).stream():
            flow_id = getattr(flow, "id", "") or ""
            short = flow_id.replace("-", "")[:8]
            if flow_id == pick or short == pick or flow_id.startswith(pick) or short.startswith(pick):
                if isinstance(flow, http.HTTPFlow) and flow.websocket is not None:
                    logging.error("ntool: '%s' is a WebSocket flow — cannot be replayed", pick)
                    continue
                writer.add(flow)
                written += 1
    logging.info("ntool: extracted %d flow(s) for '%s'", written, pick)
    ctx.master.shutdown()
