"""
Scout HTML5 Parser - Advanced HTML5 Parsing with html5lib
"""

import re
from typing import Any, Dict, List, Optional, Union, cast

from ..element import NavigableString, Tag

# html5lib is an optional dependency; import lazily at runtime to avoid hard dependency
html5lib: Any = None


class HTML5Parser:
    """
    Advanced HTML5 parser using html5lib library.
    Provides robust parsing with enhanced error handling and flexibility.
    """

    def __init__(self, namespaces: bool = False, debug: bool = False):
        """
        Initialize the HTML5 parser with advanced parsing capabilities.

        Args:
            namespaces (bool): Whether to preserve namespace information
            debug (bool): Enable debug mode for parsing
        """
        global html5lib
        if html5lib is None:
            try:
                import importlib

                html5lib = importlib.import_module("html5lib")
            except Exception as e:
                raise ImportError("html5lib is required for HTML5 parsing") from e

        self._namespaces = namespaces
        self._debug = debug
        self._parsing_errors = []

    def parse(self, markup: Union[str, bytes]) -> Tag:
        """
        Parse HTML5 markup and return the root tag.

        Args:
            markup (str | bytes): HTML5 content to parse

        Returns:
            Tag: Parsed document root
        """
        try:
            # Preprocess markup to handle common issues
            markup = self._preprocess_markup(markup)

            # Parse the markup
            tree = html5lib.parse(
                markup, namespaceHTMLElements=self._namespaces, transport_encoding="utf-8"
            )

            # Convert parsed tree to Scout Tag. html5lib may return an ElementTree or an Element
            root_elem = getattr(tree, "getroot", lambda: tree)()
            return self._convert_element(root_elem)

        except Exception as e:
            self._parsing_errors.append(str(e))
            return Tag("root")

    def _preprocess_markup(self, markup: Union[str, bytes]) -> str:
        """
        Preprocess HTML markup to handle common parsing issues.

        Args:
            markup (str): Raw HTML markup

        Returns:
            str: Preprocessed HTML markup
        """
        # Ensure we are working with a text string
        if isinstance(markup, (bytes, bytearray)):
            try:
                decoded = markup.decode("utf-8")
            except Exception:
                decoded = markup.decode("utf-8", errors="ignore")
            markup = decoded

        # Remove HTML comments
        markup = re.sub(r"<!--.*?-->", "", markup, flags=re.DOTALL)

        # Handle unclosed tags
        markup = re.sub(
            r"<(br|img|input|hr|meta)([^>]*?)(?<!/)>", r"<\1\2 />", markup, flags=re.IGNORECASE
        )

        return markup

    def _convert_element(self, element) -> Tag:
        """
        Convert html5lib element to Scout Tag.

        Args:
            element: html5lib parsed element

        Returns:
            Tag: Converted Scout Tag
        """
        # Create Tag with name and attributes
        tag = Tag(element.tag, dict(element.attrib))

        # Add text content
        if element.text:
            tag.contents.append(NavigableString(element.text))

        # Recursively add child elements
        for child in element:
            child_tag = self._convert_element(child)
            child_tag.parent = tag
            tag.contents.append(child_tag)

            # Add tail text
            if child.tail:
                tail_text = NavigableString(child.tail)
                tail_text.parent = tag
                tag.contents.append(tail_text)

        return tag

    def get_parsing_errors(self) -> List[str]:
        """
        Retrieve parsing errors encountered during processing.

        Returns:
            List[str]: List of parsing error messages
        """
        return self._parsing_errors

    def find_all(
        self,
        markup: str,
        tag: Optional[Union[str, List[str]]] = None,
        attrs: Optional[Dict[str, Any]] = None,
        recursive: bool = True,
        text: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Tag]:
        """
        Find all matching elements in the parsed document.

        Args:
            markup (str): HTML content to parse
            tag (str or List[str], optional): Tag name(s) to search for
            attrs (dict, optional): Attribute filters
            recursive (bool): Whether to search recursively
            text (str, optional): Text content to search for
            limit (int, optional): Maximum number of results

        Returns:
            List[Tag]: List of matching tags
        """
        root = self.parse(markup)

        def matches(element: Tag) -> bool:
            """Check if an element matches search criteria."""
            # Tag filter
            if tag and isinstance(tag, str) and element.name != tag:
                return False
            if tag and isinstance(tag, list) and element.name not in tag:
                return False

            # Attribute filter
            if attrs:
                for key, value in attrs.items():
                    if key not in element.attrs or element.attrs[key] != value:
                        return False

            # Text filter
            if text:
                element_text = " ".join(
                    [str(c) for c in element.contents if isinstance(c, NavigableString)]
                )
                if text not in element_text:
                    return False

            return True

        def collect_matches(element: Tag, results: List[Tag]):
            """Recursively collect matching elements."""
            if matches(element):
                results.append(element)
                if limit and len(results) >= limit:
                    return

            if recursive:
                for child in element.contents:
                    if isinstance(child, Tag):
                        collect_matches(child, results)

        results = []
        collect_matches(root, results)
        return results
