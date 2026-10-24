"""YouTube search suggestions and autocomplete."""

import json
from llm4free import LitAgent
from typing import List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from llm4free.litagent.agent import LitAgent

    _USER_AGENT = LitAgent().random()
except ImportError:
    _USER_AGENT = LitAgent().random()


class Suggestions:
    """Class for YouTube search suggestions and autocomplete."""

    AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"

    @staticmethod
    def autocomplete(query: str, language: str = "en") -> List[str]:
        """
        Get YouTube autocomplete suggestions for a search query.

        Args:
            query: Search query to get suggestions for
            language: Language code (e.g., 'en', 'es', 'fr')

        Returns:
            List of autocomplete suggestions
        """
        if not query:
            return []

        url = f"{Suggestions.AUTOCOMPLETE_URL}?client=youtube&ds=yt&q={quote(query)}&hl={language}"

        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

        try:
            req = Request(url, headers=headers)
            response = urlopen(req, timeout=10)
            data = response.read().decode("utf-8")

            # Response is JSONP, extract JSON part
            # Format: window.google.ac.h(["query",[["suggestion1"],["suggestion2"],...]])
            start = data.find("(")
            end = data.rfind(")")
            if start != -1 and end != -1:
                json_str = data[start + 1 : end]
                parsed = json.loads(json_str)
                if len(parsed) > 1 and isinstance(parsed[1], list):
                    return [item[0] for item in parsed[1] if isinstance(item, list) and item]
            return []
        except Exception:
            return []

    @staticmethod
    def trending_searches(language: str = "en", country: str = "US") -> List[str]:
        """
        Get trending YouTube searches.

        Args:
            language: Language code
            country: Country code

        Returns:
            List of trending search terms
        """
        # Get suggestions for empty-ish queries that return trending
        trending = []
        for seed in ["", "how to", "what is", "best"]:
            suggestions = Suggestions.autocomplete(seed, language)
            trending.extend(suggestions[:3])

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for item in trending:
            if item not in seen:
                seen.add(item)
                unique.append(item)

        return unique[:20]


if __name__ == "__main__":
    print("Testing autocomplete:")
    suggestions = Suggestions.autocomplete("python tutorial")
    for s in suggestions[:5]:
        print(f"  - {s}")

    print("\nTrending searches:")
    trending = Suggestions.trending_searches()
    for t in trending[:5]:
        print(f"  - {t}")
