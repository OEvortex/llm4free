import re
from llm4free import LitAgent
from typing import Any, Dict, List
from urllib.request import Request, urlopen

try:
    from llm4free.litagent.agent import LitAgent

    _USER_AGENT_GENERATOR = LitAgent()
except ImportError:
    _USER_AGENT_GENERATOR = None


class Trending:
    """Class for getting GitHub trending data (scrapes github.com/trending)"""

    BASE_URL = "https://github.com/trending"

    def get_repositories(
        self, language: str = "", since: str = "daily", spoken_language: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Get trending repositories.

        Args:
            language: Programming language filter (e.g., "python", "javascript")
            since: Time range (daily, weekly, monthly)
            spoken_language: Spoken language filter (e.g., "en" for English)

        Returns:
            List of trending repositories with name, description, stars, forks, etc.
        """
        url = self.BASE_URL
        if language:
            url += f"/{language}"
        url += f"?since={since}"
        if spoken_language:
            url += f"&spoken_language_code={spoken_language}"

        html = self._fetch_html(url)
        return self._parse_repos(html)

    def get_developers(self, language: str = "", since: str = "daily") -> List[Dict[str, Any]]:
        """
        Get trending developers.

        Args:
            language: Programming language filter
            since: Time range (daily, weekly, monthly)

        Returns:
            List of trending developers with username, name, avatar, repo
        """
        url = f"{self.BASE_URL}/developers"
        if language:
            url += f"/{language}"
        url += f"?since={since}"

        html = self._fetch_html(url)
        return self._parse_developers(html)

    def _fetch_html(self, url: str) -> str:
        """Fetch HTML content from URL."""
        headers = {
            "User-Agent": _USER_AGENT_GENERATOR.random()
            if _USER_AGENT_GENERATOR
            else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        req = Request(url, headers=headers)
        response = urlopen(req, timeout=30)
        return response.read().decode("utf-8")

    def _parse_repos(self, html: str) -> List[Dict[str, Any]]:
        """Parse trending repositories from HTML."""
        repos = []

        # Find all article elements (repo boxes) - try multiple patterns
        repo_patterns = [
            r'<article class="Box-row"[^>]*>(.*?)</article>',
            r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>',
        ]

        repo_matches = []
        for pattern in repo_patterns:
            repo_matches = re.findall(pattern, html, re.DOTALL)
            if repo_matches:
                break

        # If no matches with article, try row-based parsing
        if not repo_matches:
            # Try to find repo links directly
            repo_link_pattern = r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"[^>]*>'
            link_matches = re.findall(repo_link_pattern, html)
            for link in link_matches:
                if "/" in link and not link.startswith("topics/"):
                    parts = link.split("/")
                    if len(parts) >= 2:
                        repos.append(
                            {
                                "full_name": link,
                                "owner": parts[0],
                                "name": parts[1],
                                "description": "",
                                "language": None,
                                "stars": 0,
                                "forks": 0,
                            }
                        )
            return repos

        for repo_html in repo_matches:
            repo = {}

            # Extract repo name (owner/repo) - try multiple patterns
            name_patterns = [
                r'href="/([^"]+)"[^>]*>\s*<span[^>]*>([^<]+)</span>\s*/\s*<span[^>]*>([^<]+)</span>',
                r'href="/([^/]+/[^"]+)"[^>]*class="[^"]*Link[^"]*"',
                r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"',
            ]

            for pattern in name_patterns:
                name_match = re.search(pattern, repo_html)
                if name_match:
                    full_name = name_match.group(1).strip()
                    if "/" in full_name:
                        parts = full_name.split("/")
                        repo["full_name"] = full_name
                        repo["owner"] = parts[0].strip()
                        repo["name"] = parts[1].strip() if len(parts) > 1 else ""
                        break

            # Extract description - try multiple patterns
            desc_patterns = [
                r'<p class="[^"]*col-9[^"]*"[^>]*>([^<]+)</p>',
                r'<p class="[^"]*mb-1[^"]*"[^>]*>([^<]+)</p>',
                r'<p[^>]*class="[^"]*text-gray[^"]*"[^>]*>([^<]+)</p>',
            ]
            for pattern in desc_patterns:
                desc_match = re.search(pattern, repo_html)
                if desc_match:
                    repo["description"] = desc_match.group(1).strip()
                    break
            else:
                repo["description"] = ""

            # Extract language
            lang_patterns = [
                r'<span itemprop="programmingLanguage">([^<]+)</span>',
                r"<span[^>]*>([A-Z][a-z]+(?:\+\+|#)?)</span>\s*</span>",
            ]
            for pattern in lang_patterns:
                lang_match = re.search(pattern, repo_html)
                if lang_match:
                    repo["language"] = lang_match.group(1).strip()
                    break
            else:
                repo["language"] = None

            # Extract stars - multiple patterns
            stars_patterns = [
                r'href="/[^/]+/[^/]+/stargazers"[^>]*>\s*(?:<svg[^>]*>.*?</svg>)?\s*([\d,]+)',
                r">\s*([\d,]+)\s*</a>\s*</span>.*?stargazers",
                r"([\d,]+)\s*stars?",
            ]
            for pattern in stars_patterns:
                stars_match = re.search(pattern, repo_html, re.DOTALL)
                if stars_match:
                    repo["stars"] = int(stars_match.group(1).replace(",", ""))
                    break
            else:
                repo["stars"] = 0

            # Extract forks
            forks_patterns = [
                r'href="/[^/]+/[^/]+/forks"[^>]*>\s*(?:<svg[^>]*>.*?</svg>)?\s*([\d,]+)',
                r"([\d,]+)\s*forks?",
            ]
            for pattern in forks_patterns:
                forks_match = re.search(pattern, repo_html, re.DOTALL)
                if forks_match:
                    repo["forks"] = int(forks_match.group(1).replace(",", ""))
                    break
            else:
                repo["forks"] = 0

            # Extract stars today/this week/this month
            today_match = re.search(r"([\d,]+)\s+stars?\s+(today|this week|this month)", repo_html)
            if today_match:
                repo["stars_period"] = int(today_match.group(1).replace(",", ""))
                repo["period"] = today_match.group(2)

            if repo.get("full_name"):
                repos.append(repo)

        return repos

    def _parse_developers(self, html: str) -> List[Dict[str, Any]]:
        """Parse trending developers from HTML."""
        developers = []

        # Find all article elements (developer boxes)
        dev_pattern = r'<article class="Box-row[^"]*"[^>]*>(.*?)</article>'
        dev_matches = re.findall(dev_pattern, html, re.DOTALL)

        for dev_html in dev_matches:
            dev = {}

            # Extract username
            username_match = re.search(r'href="/([^"?]+)"[^>]*class="[^"]*Link[^"]*"', dev_html)
            if username_match:
                dev["username"] = username_match.group(1).strip()

            # Extract display name
            name_match = re.search(r'<h1 class="[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', dev_html)
            if name_match:
                dev["name"] = name_match.group(1).strip()

            # Extract avatar
            avatar_match = re.search(
                r'<img[^>]*class="[^"]*avatar[^"]*"[^>]*src="([^"]+)"', dev_html
            )
            if avatar_match:
                dev["avatar"] = avatar_match.group(1)

            # Extract popular repo
            repo_match = re.search(
                r'<span class="[^"]*css-truncate-target[^"]*"[^>]*>\s*<a href="/([^"]+)"[^>]*>([^<]+)</a>',
                dev_html,
            )
            if repo_match:
                dev["popular_repo"] = {
                    "full_name": repo_match.group(1),
                    "name": repo_match.group(2).strip(),
                }

            if dev.get("username"):
                developers.append(dev)

        return developers
