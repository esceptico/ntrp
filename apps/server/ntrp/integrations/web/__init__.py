from ntrp.config import Config
from ntrp.integrations.base import Integration, IntegrationField
from ntrp.integrations.web.tools import web_fetch_tool, web_search_tool


def _build(config: Config) -> object | None:
    mode = config.web_search
    if mode == "none":
        return None
    if mode == "ddgs":
        from ntrp.integrations.web.ddgs import DDGSWebSource

        return DDGSWebSource()
    if mode == "exa":
        if config.exa_api_key is None:
            raise ValueError("WEB_SEARCH=exa requires EXA_API_KEY")
        from ntrp.integrations.web.exa import ExaWebSource

        return ExaWebSource(api_key=config.exa_api_key)

    # auto: prefer Exa when configured, otherwise fall back to DDGS
    if config.exa_api_key:
        from ntrp.integrations.web.exa import ExaWebSource

        return ExaWebSource(api_key=config.exa_api_key)
    from ntrp.integrations.web.ddgs import DDGSWebSource

    return DDGSWebSource()


WEB = Integration(
    id="web",
    label="Web Search",
    service_fields=[
        IntegrationField("exa_api_key", "Exa", secret=True, env_var="EXA_API_KEY"),
    ],
    tools={"web_search": web_search_tool, "web_fetch": web_fetch_tool},
    build=_build,
)
