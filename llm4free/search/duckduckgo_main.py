"""DuckDuckGo unified search interface."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .base import BaseSearch
from .engines.duckduckgo.answers import DuckDuckGoAnswers
from .engines.duckduckgo.images import DuckDuckGoImages
from .engines.duckduckgo.maps import DuckDuckGoMaps
from .engines.duckduckgo.news import DuckDuckGoNews
from .engines.duckduckgo.suggestions import DuckDuckGoSuggestions
from .engines.duckduckgo.text import DuckDuckGoTextSearch
from .engines.duckduckgo.translate import DuckDuckGoTranslate
from .engines.duckduckgo.videos import DuckDuckGoVideos
from .engines.duckduckgo.weather import DuckDuckGoWeather, WeatherData
from .results import ImagesResult, NewsResult, TextResult, VideosResult


class DuckDuckGoSearch(BaseSearch):
    """Unified DuckDuckGo search interface."""

    def text(
        self,
        keywords: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        backend: str = "auto",
        max_results: Optional[int] = None,
    ) -> List[TextResult]:
        search = DuckDuckGoTextSearch()
        return search.run(keywords, region, safesearch, timelimit, backend, max_results)

    def images(
        self,
        keywords: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        size: Optional[str] = None,
        color: Optional[str] = None,
        type_image: Optional[str] = None,
        layout: Optional[str] = None,
        license_image: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[ImagesResult]:
        search = DuckDuckGoImages()
        return search.run(
            keywords,
            region,
            safesearch,
            timelimit,
            size,
            color,
            type_image,
            layout,
            license_image,
            max_results,
        )

    def videos(
        self,
        keywords: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        resolution: Optional[str] = None,
        duration: Optional[str] = None,
        license_videos: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[VideosResult]:
        search = DuckDuckGoVideos()
        return search.run(
            keywords,
            region,
            safesearch,
            timelimit,
            resolution,
            duration,
            license_videos,
            max_results,
        )

    def news(
        self,
        keywords: str,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        timelimit: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> List[NewsResult]:
        search = DuckDuckGoNews()
        return search.run(keywords, region, safesearch, timelimit, max_results)

    def answers(self, keywords: str) -> List[Dict[str, str]]:
        search = DuckDuckGoAnswers()
        return search.run(keywords)

    def suggestions(self, keywords: str, region: str = "wt-wt") -> List[Dict[str, str]]:
        search = DuckDuckGoSuggestions()
        return search.run(keywords, region)

    def maps(
        self,
        keywords: str,
        place: Optional[str] = None,
        street: Optional[str] = None,
        city: Optional[str] = None,
        county: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        postalcode: Optional[str] = None,
        latitude: Optional[str] = None,
        longitude: Optional[str] = None,
        radius: int = 0,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        search = DuckDuckGoMaps()
        return search.run(
            keywords,
            place,
            street,
            city,
            county,
            state,
            country,
            postalcode,
            latitude,
            longitude,
            radius,
            max_results,
        )

    def translate(
        self, keywords: str, from_lang: Optional[str] = None, to_lang: str = "en"
    ) -> List[Dict[str, str]]:
        search = DuckDuckGoTranslate()
        return search.run(keywords, from_lang, to_lang)

    def weather(self, keywords: str) -> WeatherData:
        search = DuckDuckGoWeather()
        return search.run(keywords)
