from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ntrp.server.runtime import Runtime, get_runtime
from ntrp.services.config import ConfigService

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _require_config_service(runtime: Runtime = Depends(get_runtime)) -> ConfigService:
    if not runtime.config_service:
        raise HTTPException(status_code=503, detail="Config service not available")
    return runtime.config_service


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
    cfg_svc: ConfigService = Depends(_require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if req.name in existing:
        raise HTTPException(status_code=409, detail=f"MCP server {req.name!r} already exists")

    from ntrp.mcp.models import parse_server_config

    try:
        parse_server_config(req.name, req.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        await cfg_svc.add_mcp_server(req.name, req.config)
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
    cfg_svc: ConfigService = Depends(_require_config_service),
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


@router.delete("/servers/{name}")
async def remove_mcp_server(
    name: str,
    runtime: Runtime = Depends(get_runtime),
    cfg_svc: ConfigService = Depends(_require_config_service),
):
    existing = runtime.config.mcp_servers or {}
    if name not in existing:
        raise HTTPException(status_code=404, detail=f"MCP server {name!r} not found")

    try:
        await cfg_svc.remove_mcp_server(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "removed", "name": name}
