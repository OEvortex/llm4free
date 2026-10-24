"""
Scout Parsers - Unified Parsing Interfaces
"""

from typing import Any, Dict, Optional, Type

from .html5lib_parser import HTML5Parser
from .html_parser import HTMLParser
from .lxml_parser import LXMLParser


class ParserRegistry:
    """
    Centralized parser registry for Scout library.
    Manages and provides access to different HTML parsing strategies.
    """

    _PARSERS: Dict[str, Type[Any]] = {
        "html.parser": HTMLParser,
        "lxml": LXMLParser,
    }

    @classmethod
    def _ensure_html5lib(cls) -> None:
        """Register html5lib parser only if the html5lib package is importable."""
        if "html5lib" in cls._PARSERS:
            return
        try:
            import importlib

            importlib.import_module("html5lib")
            cls._PARSERS["html5lib"] = HTML5Parser
        except ImportError:
            # html5lib is optional; leave it unregistered so callers get a
            # clear error when they explicitly request it.
            pass

    @classmethod
    def get_parser(cls, parser_name: str = "html.parser") -> Any:
        """
        Retrieve a parser by its name.

        Args:
            parser_name (str): Name of the parser to retrieve

        Returns:
            Parser instance

        Raises:
            ValueError: If the parser is not found
        """
        if parser_name == "html5lib":
            cls._ensure_html5lib()
        if parser_name not in cls._PARSERS:
            if parser_name == "html5lib":
                raise ImportError(
                    "html5lib is required for the 'html5lib' parser but is not installed. "
                    "Install it with: pip install html5lib"
                )
            raise ValueError(
                f"Parser '{parser_name}' not found. Available parsers: {list(cls._PARSERS.keys())}"
            )

        return cls._PARSERS[parser_name]()

    @classmethod
    def register_parser(cls, name: str, parser_class: Type[Any]):
        """
        Register a new parser dynamically.

        Args:
            name (str): Name of the parser
            parser_class (Type[Any]): Parser class to register
        """
        cls._PARSERS[name] = parser_class

    @classmethod
    def list_parsers(cls) -> Dict[str, Type[Any]]:
        """
        List all registered parsers.

        Returns:
            Dict of available parsers
        """
        cls._ensure_html5lib()
        return cls._PARSERS.copy()


# Expose key classes and functions
__all__ = ["HTMLParser", "LXMLParser", "HTML5Parser", "ParserRegistry"]
