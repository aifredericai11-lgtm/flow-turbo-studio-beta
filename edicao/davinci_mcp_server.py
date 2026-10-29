"""
Servidor MCP (Model Context Protocol - stdio) para o DaVinci Resolve + Esteira de Edição.
Expõe ferramentas para verificar conexão com o DaVinci Resolve, sincronizar timelines 1080x1920
e renderizar takes direto da esteira.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from edicao.davinci_bridge import conectar_davinci, sincronizar_timeline_davinci


TOOLS = [
    {
        "name": "davinci_status",
        "description": "Verifica se o DaVinci Resolve está aberto e conectado via fusionscript.dll / DaVinciResolveScript.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "davinci_sync_timeline",
        "description": "Cria/sincroniza uma timeline vertical 1080x1920 (30fps) no DaVinci Resolve (e gera .fcpxml) a partir de uma lista de clipes MP4.",
        "inputSchema": {
            "type": "object",
            "required": ["nome_timeline", "clipes"],
            "properties": {
                "nome_projeto": {"type": "string", "default": "Esteira_Forja_Edicao"},
                "nome_timeline": {"type": "string"},
                "clipes": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
]


def _handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "davinci-resolve-mcp", "version": "1.0.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "davinci_status":
            resolve, msg = conectar_davinci()
            payload = {"conectado": resolve is not None, "mensagem": msg}
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]},
            }
        if name == "davinci_sync_timeline":
            clipes_paths = [Path(p) for p in args.get("clipes", [])]
            res = sincronizar_timeline_davinci(
                nome_projeto=args.get("nome_projeto", "Esteira_Forja_Edicao"),
                nome_timeline=args["nome_timeline"],
                clipes_cortados=clipes_paths,
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]},
            }
    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = _handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            sys.stderr.write(f"MCP error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
