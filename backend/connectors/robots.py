import httpx
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from ..config import USER_AGENT


class RobotsCache:
    """Fail-closed robots.txt checker."""

    def __init__(self):
        self._parsers = {}

    async def allowed(self, url: str) -> bool:
        u = urlparse(url)
        base = f"{u.scheme}://{u.netloc}"
        if base not in self._parsers:
            rp = RobotFileParser()
            try:
                async with httpx.AsyncClient(timeout=5, headers={"User-Agent": USER_AGENT}) as c:
                    r = await c.get(base + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:
                rp.parse(["User-agent: *", "Disallow: /"])
            rp.modified()
            self._parsers[base] = rp
        return self._parsers[base].can_fetch(USER_AGENT, url)


robots = RobotsCache()
