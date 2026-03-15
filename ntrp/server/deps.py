from fastapi import Depends, HTTPException

from ntrp.server.runtime import Runtime, get_runtime


def require_memory(runtime: Runtime = Depends(get_runtime)):
    if not runtime.memory_service:
        if runtime.config.memory:
            detail = "Memory is unavailable — configure an embedding model from OpenAI or Google"
        else:
            detail = "Memory is disabled"
        raise HTTPException(status_code=503, detail=detail)
    return runtime.memory_service


def require_session_service(runtime: Runtime = Depends(get_runtime)):
    if not runtime.session_service:
        raise HTTPException(status_code=503, detail="Session service not available")
    return runtime.session_service


def require_config_service(runtime: Runtime = Depends(get_runtime)):
    if not runtime.config_service:
        raise HTTPException(status_code=503, detail="Config service not available")
    return runtime.config_service


def require_automation_service(runtime: Runtime = Depends(get_runtime)):
    if not runtime.automation_service:
        raise HTTPException(status_code=503, detail="Automations not available")
    return runtime.automation_service


def require_notifier_service(runtime: Runtime = Depends(get_runtime)):
    if not runtime.notifier_service:
        raise HTTPException(status_code=503, detail="Notifier service not available")
    return runtime.notifier_service


def require_skill_service(runtime: Runtime = Depends(get_runtime)):
    if not runtime.skill_service:
        raise HTTPException(status_code=503, detail="Skill service not available")
    return runtime.skill_service
