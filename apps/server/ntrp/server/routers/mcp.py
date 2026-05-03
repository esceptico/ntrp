import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ntrp.mcp.models import HttpTransport, parse_server_config
from ntrp.mcp.oauth import OAuthOptions, clear_tokens, run_mcp_oauth
from ntrp.server.deps import require_config_service
from ntrp.server.runtime import Runtime, get_runtime
from ntrp.services.config import ConfigService

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers")
async def list_mcp_servers(runtime: Runtime = Depends(get_runtime)):
    configs = runtime.config.mcp_servers or {}
    manager = runtime.mcp_manager
    servers = []
    for name, raw in configs.items():
        session = manager.sessions.get(name) if manager else None
        error = manager.errors.get(name) if manager else None
        whitelist = raw.get("tools")
        allowed = set(whitelist) if whitelist is not None else None
        tools = []
        if session and session.connected:
            for t in session.all_tools:
                tools.append(
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "enabled": allowed is None or t.name in allowed,
                    }
                )
        servers.append(
            {
                "name": name,
                "transport": raw.get("transport", "unknown"),
                "connected": session.connected if session else False,
                "tool_count": len(session.tools) if session else 0,
                "error": error,
                "command": raw.get("command"),
                "args": raw.get("args"),
                "url": raw.get("url"),
                "tools": tools,
                "enabled": raw.get("enabled", True),
                "auth": raw.get("auth"),
                "has_client_credentials": bool(raw.get("client_id")),
            }
        )
    return {"servers": servers}


class AddMCPServerRequest(BaseModel):
    name: str
    config: dict


@router.post("/servers")
async def add_mcp_server(
    req: AddMCPServerRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if req.name in existing:
        raise HTTPException(status_code=409, detail=f"MCP server {req.name!r} already exists")

    try:
        parsed = parse_server_config(req.name, req.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = dict(req.config)
    if isinstance(parsed.transport, HttpTransport):
        config["url"] = parsed.transport.url

    try:
        await cfg_svc.add_mcp_server(req.name, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    manager = runtime.mcp_manager
    session = manager.sessions.get(req.name) if manager else None
    error = manager.errors.get(req.name) if manager else None
    return {
        "status": "added",
        "name": req.name,
        "connected": session.connected if session else False,
        "tool_count": len(session.tools) if session else 0,
        "error": error,
    }


class UpdateToolsRequest(BaseModel):
    tools: list[str] | None


@router.put("/servers/{name}/tools")
async def update_mcp_tools(
    name: str,
    req: UpdateToolsRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"MCP server {name!r} not found")

    config = dict(existing[name])
    if req.tools is not None:
        config["tools"] = req.tools
    else:
        config.pop("tools", None)

    try:
        await cfg_svc.update_mcp_server(name, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "updated", "name": name, "tool_count": len(req.tools) if req.tools else None}


class ToggleEnabledRequest(BaseModel):
    enabled: bool


@router.put("/servers/{name}/enabled")
async def toggle_mcp_server(
    name: str,
    req: ToggleEnabledRequest,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"MCP server {name!r} not found")

    try:
        await cfg_svc.toggle_mcp_server(name, req.enabled)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "toggled", "name": name, "enabled": req.enabled}


@router.post("/servers/{name}/oauth")
async def mcp_oauth(
    name: str,
    runtime: Runtime = Depends(get_runtime),
):
    existing = runtime.config.mcp_servers or {}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"MCP server {name!r} not found")

    raw = existing[name]
    try:
        parsed = parse_server_config(name, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    transport = parsed.transport
    if not isinstance(transport, HttpTransport) or transport.auth != "oauth":
        raise HTTPException(status_code=400, detail="Server does not use OAuth authentication")

    opts = OAuthOptions(
        client_id=transport.client_id,
        client_secret=transport.client_secret,
        redirect_port=transport.redirect_port,
        scope=transport.scope,
        client_name=transport.client_name or "NTRP",
    )
    try:
        await asyncio.to_thread(run_mcp_oauth, name, transport.url, opts)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Reconnect MCP servers to pick up the new tokens
    await runtime.sync_mcp()

    manager = runtime.mcp_manager
    session = manager.sessions.get(name) if manager else None
    error = manager.errors.get(name) if manager else None
    return {
        "status": "connected",
        "name": name,
        "connected": session.connected if session else False,
        "tool_count": len(session.tools) if session else 0,
        "error": error,
    }


@router.delete("/servers/{name}")
async def remove_mcp_server(
    name: str,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"MCP server {name!r} not found")

    try:
        await cfg_svc.remove_mcp_server(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Clean up OAuth tokens if any
    clear_tokens(name)

    return {"status": "removed", "name": name}
