# -*- coding: utf-8 -*-
"""MCP 协议探针 —— 实测 WorkBuddy 到底用哪一代协议、发什么能力声明。

原理：这是个最小 stdio MCP server，把 WorkBuddy 发来的**每一行原始 JSON-RPC**
原样记录下来，同时礼貌地回应（否则客户端会认为服务器坏了）。

装到 WorkBuddy 的 ~/.workbuddy/mcp.json 后，在对话里随便问一句触发一次，
然后把日志文件发我，就能 100% 确定：
  · 是否发 initialize（=legacy）还是 server/discover（=modern）
  · 声明的 protocolVersion 是什么
  · clientInfo（名称/版本）、capabilities
  · 它是否会调用 tools/list、tools/call

用法：python mcp_probe.py            （由 WorkBuddy 以 stdio 方式拉起）
日志：与脚本同目录的 mcp_probe_log.jsonl
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "mcp_probe_log.jsonl")

# 我们能"假装"支持的最高版本（legacy 时代的正式版本）
LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]


def log(obj):
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **obj},
                           ensure_ascii=False) + "\n")


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def reply(mid, result):
    send({"jsonrpc": "2.0", "id": mid, "result": result})


def main():
    log({"event": "start", "argv": sys.argv, "cwd": os.getcwd(),
         "python": sys.version.split()[0]})
    for line in sys.stdin:
        # 去掉 BOM / 首尾空白：实测踩过坑 —— PowerShell 管道会在首行前置 U+FEFF，
        # 导致第一行（往往是 initialize）被当成非 JSON 丢掉。
        line = line.lstrip("\ufeff").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            log({"event": "non-json-line", "raw": line[:800]})
            continue

        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        # 全量记录（含 _meta，modern 协议的关键在这里）
        log({"event": "recv", "method": method, "id": mid,
             "params_keys": sorted(params.keys()),
             "meta": params.get("_meta"),
             "protocolVersion": params.get("protocolVersion"),
             "clientInfo": params.get("clientInfo"),
             "capabilities": params.get("capabilities")})

        if method == "initialize":
            want = params.get("protocolVersion")
            ver = want if want in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
            reply(mid, {
                "protocolVersion": ver,
                "capabilities": {"tools": {"listChanged": False},
                                 "resources": {"subscribe": False, "listChanged": False},
                                 "prompts": {"listChanged": False}},
                "serverInfo": {"name": "ebay-probe", "version": "0.0.1"},
                "instructions": "协议探针：仅用于记录客户端行为。",
            })
            continue

        if method == "notifications/initialized":
            log({"event": "handshake-complete"})
            continue

        if method == "server/discover":          # modern 时代的探测
            reply(mid, {"protocolVersions": LEGACY_VERSIONS + ["2026-07-28"],
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ebay-probe", "version": "0.0.1"}})
            continue

        if method == "tools/list":
            reply(mid, {"tools": [{
                "name": "probe_ping",
                "title": "协议探针",
                "description": "仅用于确认 WorkBuddy 是否能成功调用工具。返回一行确认信息。",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                "idempotentHint": True, "openWorldHint": False},
            }]})
            continue

        if method == "tools/call":
            log({"event": "tool-call", "name": params.get("name"),
                 "arguments": params.get("arguments")})
            reply(mid, {"content": [{"type": "text",
                                     "text": "探针收到调用 ✅ WorkBuddy 与本 server 通信正常。"}],
                        "isError": False})
            continue

        if method in ("resources/list", "prompts/list"):
            reply(mid, {"resources": []} if method.startswith("resources")
                  else {"prompts": []})
            continue

        if mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": "probe: %s not implemented" % method}})

    log({"event": "stdin-closed"})


if __name__ == "__main__":
    main()
