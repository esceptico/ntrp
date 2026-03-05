import html
import re
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ddgs import DDGS

from ntrp.sources.base import Source, WebContentResult, WebSearchResult, WebSearchSource

_MAX_FETCH_BYTES = 1_000_000


def _extract_title(raw_html: str, default: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return default
    title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    return title or default


def _extract_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _guess_title(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


class DDGSWebSource(Source, WebSearchSource):
    name = "web"
    provider = "ddgs"

    def search_with_details(
        self,
        query: str,
        num_results: int = 5,
        category: str | None = None,
    ) -> list[WebSearchResult]:
        del category
        results: list[WebSearchResult] = []
        with DDGS() as client:
            items = client.text(query, max_results=num_results) or []
            for item in items:
                title = (item.get("title") or item.get("heading") or "").strip()
                url = (item.get("href") or item.get("url") or "").strip()
                snippet = (item.get("body") or item.get("snippet") or "").strip()
                published = item.get("date")
                if not url:
                    continue
                if not title:
                    title = _guess_title(url)
                highlights = [snippet] if snippet else None
                results.append(
                    WebSearchResult(
                        title=title,
                        url=url,
                        published_date=str(published) if published else None,
                        summary=snippet or None,
                        highlights=highlights,
                    )
                )
        return results

    def get_contents(self, urls: list[str]) -> list[WebContentResult]:
        out: list[WebContentResult] = []
        for url in urls:
            try:
                req = Request(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                        )
                    },
                )
                with urlopen(req, timeout=10) as resp:
                    raw_bytes = resp.read(_MAX_FETCH_BYTES)
                    content_type = resp.headers.get("Content-Type", "")
                raw = raw_bytes.decode("utf-8", errors="replace")
                if "text/html" in content_type.lower() or "<html" in raw.lower():
                    title = _extract_title(raw, _guess_title(url))
                    text = _extract_text(raw)
                else:
                    title = _guess_title(url)
                    text = raw.strip()
                out.append(
                    WebContentResult(
                        title=title,
                        url=url,
                        text=text or None,
                        published_date=None,
                        author=None,
                    )
                )
            except (ValueError, URLError, TimeoutError, OSError):
                out.append(
                    WebContentResult(
                        title=_guess_title(url),
                        url=url,
                        text=None,
                        published_date=None,
                        author=None,
                    )
                )
        return out
