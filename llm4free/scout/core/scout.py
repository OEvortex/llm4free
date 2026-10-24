"""
Scout Main Module - HTML Parsing and Traversal
"""

import hashlib
import json
import re
import unicodedata
import urllib.parse
from typing import Any, Dict, List, Literal, Optional, Union

from ..element import NavigableString, Tag
from ..parsers import ParserRegistry
from ..utils import decode_markup
from .search_result import ScoutSearchResult
from .text_analyzer import ScoutTextAnalyzer
from .web_analyzer import ScoutWebAnalyzer


class Scout:
    """
    Scout - Making web scraping a breeze! 🌊
    A comprehensive HTML parsing and traversal library.
    Enhanced with advanced features and intelligent parsing.
    """

    def __init__(
        self,
        markup: Union[str, bytes] = "",
        features: str = "html.parser",
        from_encoding: Optional[str] = None,
        exclude_encodings: Optional[List[str]] = None,
        element_classes: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize Scout with HTML content.

        Args:
            markup (str): HTML content to parse
            features (str): Parser to use ('html.parser', 'lxml', 'html5lib', 'lxml-xml').
                              'html5lib' requires the optional html5lib package.
            from_encoding (str): Source encoding (if known)
            exclude_encodings (list): Encodings to avoid
            element_classes (dict): Custom classes for different element types
            **kwargs: Additional parsing options
        """
        # Store original markup and settings
        self.original_encoding = from_encoding
        self.exclude_encodings = exclude_encodings or []
        self.element_classes = element_classes or {}
        self.builder_features = features
        self.contains_replacement_characters = False

        # Intelligent markup handling
        self.markup = self._preprocess_markup(markup, from_encoding)
        self.features = features
        self.from_encoding = from_encoding

        # Get the right parser for the job
        known_parsers = {"html.parser", "lxml", "html5lib", "lxml-xml"}
        if features not in known_parsers:
            raise ValueError(
                f"Invalid parser '{features}'! Choose from: {', '.join(sorted(known_parsers))}"
            )

        # html5lib is optional; importing it may raise ImportError if not installed
        parser_class = ParserRegistry.get_parser(features)
        self.parser = parser_class

        # Parse that HTML! 🎯
        self._soup = self.parser.parse(self.markup)

        # Set up the root element properly
        if hasattr(self._soup, "name"):
            self.name = self._soup.name
        else:
            self.name = "[document]"

        # BS4-like attributes
        self.attrs = self._soup.attrs if hasattr(self._soup, "attrs") else {}
        self.contents = self._soup.contents if hasattr(self._soup, "contents") else []
        self.parent = None
        self.next_sibling = None
        self.previous_sibling = None

        # Advanced parsing options and caching
        self._cache = {}
        self._tag_name_cache = {}
        self._css_selector_cache = {}

        # Text and web analyzers
        self.text_analyzer = ScoutTextAnalyzer()
        self.web_analyzer = ScoutWebAnalyzer()

    def normalize_text(
        self, text: str, form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFKD"
    ) -> str:
        """
        Normalize text using Unicode normalization.

        Args:
            text (str): Input text
            form (Literal["NFC", "NFD", "NFKC", "NFKD"], optional): Normalization form

        Returns:
            str: Normalized text
        """
        return unicodedata.normalize(form, text)

    def url_parse(self, url: str) -> Dict[str, str]:
        """
        Parse and analyze a URL.

        Args:
            url (str): URL to parse

        Returns:
            Dict[str, str]: Parsed URL components
        """
        parsed = urllib.parse.urlparse(url)
        return {
            "scheme": parsed.scheme,
            "netloc": parsed.netloc,
            "path": parsed.path,
            "params": parsed.params,
            "query": parsed.query,
            "fragment": parsed.fragment,
        }

    def analyze_page_structure(self) -> Dict[str, Any]:
        """
        Analyze the structure of the parsed page.

        Returns:
            Dict[str, Any]: Page structure analysis
        """
        return self.web_analyzer.analyze_page_structure(self)

    def analyze_text(self, text: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform advanced text analysis.

        Args:
            text (str, optional): Text to analyze. If None, uses page text.

        Returns:
            Dict[str, Any]: Text analysis results
        """
        if text is None:
            text = self.get_text()

        return {
            "word_count": self.text_analyzer.count_words(text),
            "entities": self.text_analyzer.extract_entities(text),
            "tokens": self.text_analyzer.tokenize(text),
        }

    def extract_semantic_info(self) -> Dict[str, Any]:
        """
        Extract semantic information from the document.

        Returns:
            Dict[str, Any]: Semantic information
        """
        semantic_info = {
            "headings": {
                "h1": [h.get_text(strip=True) for h in self.find_all("h1")],
                "h2": [h.get_text(strip=True) for h in self.find_all("h2")],
                "h3": [h.get_text(strip=True) for h in self.find_all("h3")],
            },
            "lists": {
                "ul": [ul.find_all("li") for ul in self.find_all("ul")],
                "ol": [ol.find_all("li") for ol in self.find_all("ol")],
            },
            "tables": {
                "count": len(self.find_all("table")),
                "headers": [table.find_all("th") for table in self.find_all("table")],
            },
        }
        return semantic_info

    def cache(self, key: str, value: Any = None) -> Any:
        """
        Manage a cache for parsed content.

        Args:
            key (str): Cache key
            value (Any, optional): Value to cache

        Returns:
            Any: Cached value or None
        """
        if value is not None:
            self._cache[key] = value
        return self._cache.get(key)

    def hash_content(self, method="md5") -> str:
        """
        Generate a hash of the parsed content.

        Args:
            method (str, optional): Hashing method

        Returns:
            str: Content hash
        """
        hash_methods = {"md5": hashlib.md5, "sha1": hashlib.sha1, "sha256": hashlib.sha256}

        if method not in hash_methods:
            raise ValueError(f"Unsupported hash method: {method}")

        hasher = hash_methods[method]()
        hasher.update(str(self._soup).encode("utf-8"))
        return hasher.hexdigest()

    def extract_links(self, base_url: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Extract all links from the document.

        Args:
            base_url (str, optional): Base URL for resolving relative links

        Returns:
            List[Dict[str, str]]: List of link dictionaries
        """
        links = []
        for link in self.find_all(["a", "link"]):
            href = link.get("href")
            if href:
                # Resolve relative URLs if base_url is provided
                if base_url and not href.startswith(("http://", "https://", "//")):
                    href = f"{base_url.rstrip('/')}/{href.lstrip('/')}"

                links.append(
                    {
                        "href": href,
                        "text": link.get_text(strip=True),
                        "rel": link.get("rel", [None])[0],
                        "type": link.get("type"),
                    }
                )
        return links

    def extract_metadata(self) -> Dict[str, Any]:
        """
        Extract metadata from HTML document.

        Returns:
            Dict[str, Any]: Extracted metadata
        """
        title_tag = self.find("title")
        desc_tag = self.find("meta", attrs={"name": "description"})
        keywords_tag = self.find("meta", attrs={"name": "keywords"})

        metadata = {
            "title": title_tag.get_text(strip=True) if title_tag else None,
            "description": desc_tag.get("content") if desc_tag else None,
            "keywords": keywords_tag.get("content").split(",")
            if keywords_tag and keywords_tag.get("content")
            else [],
            "og_metadata": {},
            "twitter_metadata": {},
        }

        # Open Graph metadata
        for meta in self.find_all("meta", attrs={"property": re.compile(r"^og:")}):
            key = meta.get("property")
            if key and key.startswith("og:"):
                if isinstance(metadata["og_metadata"], dict):
                    metadata["og_metadata"][key[3:]] = meta.get("content")

        # Twitter Card metadata
        for meta in self.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
            key = meta.get("name")
            if key and key.startswith("twitter:"):
                if isinstance(metadata["twitter_metadata"], dict):
                    metadata["twitter_metadata"][key[8:]] = meta.get("content")

        return metadata

    def to_json(self, indent=2) -> str:
        """
        Convert parsed content to JSON.

        Args:
            indent (int, optional): JSON indentation

        Returns:
            str: JSON representation of the document
        """

        def _tag_to_dict(tag):
            if isinstance(tag, NavigableString):
                return str(tag)

            result = {"name": tag.name, "attrs": tag.attrs, "text": tag.get_text(strip=True)}

            if tag.contents:
                result["children"] = [_tag_to_dict(child) for child in tag.contents]

            return result

        return json.dumps(_tag_to_dict(self._soup), indent=indent)

    def find(
        self, name=None, attrs={}, recursive=True, text=None, class_=None, **kwargs
    ) -> Optional[Tag]:
        """
        Find the first matching element. Returns a single Tag or None.
        Highly compatible with BS4.
        """
        return self._soup.find(name, attrs, recursive, text, limit=1, class_=class_, **kwargs)

    def find_all(
        self, name=None, attrs={}, recursive=True, text=None, limit=None, class_=None, **kwargs
    ) -> ScoutSearchResult:
        """
        Find all matching elements.

        Args:
            name (str, optional): Tag name to search for
            attrs (dict, optional): Attributes to match
            recursive (bool, optional): Search recursively
            text (str, optional): Text content to match
            limit (int, optional): Maximum number of results

        Returns:
            ScoutSearchResult: List of matching elements
        """
        results = self._soup.find_all(name, attrs, recursive, text, limit, class_=class_, **kwargs)
        return ScoutSearchResult(results)

    def find_parent(self, name=None, attrs={}, **kwargs) -> Optional[Tag]:
        """
        Find the first parent matching given criteria.

        Args:
            name (str, optional): Tag name to search for
            attrs (dict, optional): Attributes to match

        Returns:
            Tag or None: First matching parent
        """
        current = self._soup.parent
        while current:
            if (name is None or current.name == name) and all(
                current.get(k) == v for k, v in attrs.items()
            ):
                return current
            current = current.parent
        return None

    def find_parents(self, name=None, attrs={}, limit=None, **kwargs) -> List[Tag]:
        """
        Find all parents matching given criteria.

        Args:
            name (str, optional): Tag name to search for
            attrs (dict, optional): Attributes to match
            limit (int, optional): Maximum number of results

        Returns:
            List[Tag]: List of matching parents
        """
        parents = []
        current = self._soup.parent
        while current and (limit is None or len(parents) < limit):
            if (name is None or current.name == name) and all(
                current.get(k) == v for k, v in attrs.items()
            ):
                parents.append(current)
            current = current.parent
        return parents

    def find_next_sibling(self, name=None, attrs={}, **kwargs) -> Optional[Tag]:
        """
        Find the next sibling matching given criteria.

        Args:
            name (str, optional): Tag name to search for
            attrs (dict, optional): Attributes to match

        Returns:
            Tag or None: First matching next sibling
        """
        if not self._soup.parent:
            return None

        siblings = self._soup.parent.contents
        try:
            current_index = siblings.index(self._soup)
            for sibling in siblings[current_index + 1 :]:
                if isinstance(sibling, Tag):
                    if (name is None or sibling.name == name) and all(
                        sibling.get(k) == v for k, v in attrs.items()
                    ):
                        return sibling
        except ValueError:
            pass
        return None

    def find_next_siblings(self, name=None, attrs={}, limit=None, **kwargs) -> List[Tag]:
        """
        Find all next siblings matching given criteria.

        Args:
            name (str, optional): Tag name to search for
            attrs (dict, optional): Attributes to match
            limit (int, optional): Maximum number of results

        Returns:
            List[Tag]: List of matching next siblings
        """
        if not self._soup.parent:
            return []

        siblings = []
        siblings_list = self._soup.parent.contents
        try:
            current_index = siblings_list.index(self._soup)
            for sibling in siblings_list[current_index + 1 :]:
                if isinstance(sibling, Tag):
                    if (name is None or sibling.name == name) and all(
                        sibling.get(k) == v for k, v in attrs.items()
                    ):
                        siblings.append(sibling)
                        if limit and len(siblings) == limit:
                            break
        except ValueError:
            pass
        return siblings

    def find_previous_sibling(self, name=None, attrs={}, **kwargs) -> Optional[Tag]:
        """Find the previous sibling matching given criteria."""
        if not self._soup.parent:
            return None

        siblings = self._soup.parent.contents
        try:
            current_index = siblings.index(self._soup)
            for sibling in reversed(siblings[:current_index]):
                if isinstance(sibling, Tag):
                    if (name is None or sibling.name == name) and all(
                        sibling.get(k) == v for k, v in attrs.items()
                    ):
                        return sibling
        except ValueError:
            pass
        return None

    def find_previous_siblings(self, name=None, attrs={}, limit=None, **kwargs) -> List[Tag]:
        """Find all previous siblings matching given criteria."""
        if not self._soup.parent:
            return []

        siblings = []
        siblings_list = self._soup.parent.contents
        try:
            current_index = siblings_list.index(self._soup)
            for sibling in reversed(siblings_list[:current_index]):
                if isinstance(sibling, Tag):
                    if (name is None or sibling.name == name) and all(
                        sibling.get(k) == v for k, v in attrs.items()
                    ):
                        siblings.append(sibling)
                        if limit and len(siblings) == limit:
                            break
        except ValueError:
            pass
        return siblings

    def find_next(self, name=None, attrs={}, text=None, **kwargs) -> Optional[Tag]:
        """
        Find the next element in document order.

        Args:
            name: Tag name to search for
            attrs: Attributes to match
            text: Text content to match
            **kwargs: Additional attributes

        Returns:
            Optional[Tag]: Next matching element or None
        """
        return self._soup.find_next(name, attrs, text, **kwargs)

    def find_all_next(self, name=None, attrs={}, text=None, limit=None, **kwargs) -> List[Tag]:
        """
        Find all next elements in document order.

        Args:
            name: Tag name to search for
            attrs: Attributes to match
            text: Text content to match
            limit: Maximum number of results
            **kwargs: Additional attributes

        Returns:
            List[Tag]: List of matching elements
        """
        return self._soup.find_all_next(name, attrs, text, limit, **kwargs)

    def find_previous(self, name=None, attrs={}, text=None, **kwargs) -> Optional[Tag]:
        """
        Find the previous element in document order.

        Args:
            name: Tag name to search for
            attrs: Attributes to match
            text: Text content to match
            **kwargs: Additional attributes

        Returns:
            Optional[Tag]: Previous matching element or None
        """
        return self._soup.find_previous(name, attrs, text, **kwargs)

    def find_all_previous(self, name=None, attrs={}, text=None, limit=None, **kwargs) -> List[Tag]:
        """
        Find all previous elements in document order.

        Args:
            name: Tag name to search for
            attrs: Attributes to match
            text: Text content to match
            limit: Maximum number of results
            **kwargs: Additional attributes

        Returns:
            List[Tag]: List of matching elements
        """
        return self._soup.find_all_previous(name, attrs, text, limit, **kwargs)

    def select(self, selector: str) -> List[Tag]:
        """
        Select elements using CSS selector.

        Args:
            selector (str): CSS selector string

        Returns:
            List[Tag]: List of matching elements
        """
        return self._soup.select(selector)

    def select_one(self, selector: str) -> Optional[Tag]:
        """
        Select the first element matching the CSS selector.

        Args:
            selector (str): CSS selector string

        Returns:
            Tag or None: First matching element
        """
        return self._soup.select_one(selector)

    def get_text(self, separator="", strip=False, types=None) -> str:
        """
        Extract all text from the parsed document.
        Standard behavior like BS4.
        """
        return self._soup.get_text(separator, strip, types)

    @property
    def text(self) -> str:
        """BS4 compatible text property."""
        return self.get_text()

    @property
    def string(self) -> Optional[str]:
        """BS4 compatible string property."""
        return self._soup.string

    def get_text_robust(
        self, separator=" ", strip=False, types=None, encoding_fallbacks=None
    ) -> str:
        """Extract text robustly, trying multiple encodings if needed."""
        try:
            return self.get_text(separator, strip, types)
        except UnicodeDecodeError:
            if encoding_fallbacks:
                for enc in encoding_fallbacks:
                    try:
                        return self._soup.get_text(separator, strip, types).encode(enc).decode(enc)
                    except Exception:
                        continue
            raise

    def remove_tags(self, tags: List[str]) -> None:
        """
        Remove specified tags and their contents from the document.

        Args:
            tags (List[str]): List of tag names to remove
        """
        for tag_name in tags:
            for tag in self._soup.find_all(tag_name):
                tag.decompose()

    def prettify(self, formatter="minimal") -> str:
        """
        Return a formatted, pretty-printed version of the HTML.

        Args:
            formatter (str, optional): Formatting style

        Returns:
            str: Prettified HTML
        """
        return self._soup.prettify(formatter)

    def decompose(self, tag: Optional[Tag] = None) -> None:
        """
        Remove a tag and its contents from the document.

        Args:
            tag (Tag, optional): Tag to remove. If None, removes the root tag.
        """
        if tag is None:
            tag = self._soup
        assert tag is not None
        tag.decompose()

    def extract(self, tag: Optional[Tag] = None) -> Tag:
        """
        Remove a tag from the document and return it.

        Args:
            tag (Tag, optional): Tag to extract. If None, extracts the root tag.

        Returns:
            Tag: Extracted tag
        """
        if tag is None:
            tag = self._soup
        assert tag is not None
        return tag.extract()

    def clear(self, tag: Optional[Tag] = None) -> None:
        """
        Remove a tag's contents while keeping the tag itself.

        Args:
            tag (Tag, optional): Tag to clear. If None, clears the root tag.
        """
        if tag is None:
            tag = self._soup
        assert tag is not None
        tag.clear()

    def replace_with(self, old_tag: Tag, new_tag: Tag) -> None:
        """
        Replace one tag with another.

        Args:
            old_tag (Tag): Tag to replace
            new_tag (Tag): Replacement tag
        """
        old_tag.replace_with(new_tag)

    def encode(self, encoding="utf-8", errors="strict") -> bytes:
        """Encode the document to a specific encoding with error handling."""
        try:
            return str(self._soup).encode(encoding, errors)
        except Exception:
            return str(self._soup).encode("utf-8", errors)

    def decode(self, encoding="utf-8", errors="strict") -> str:
        """Decode the document from a specific encoding with error handling.

        Note: The parsed soup is represented as a str in memory, so decoding
        simply returns the string representation.
        """
        try:
            return str(self._soup)
        except Exception:
            return str(self._soup)

    def __str__(self) -> str:
        """
        String representation of the parsed document.

        Returns:
            str: HTML content
        """
        return str(self._soup)

    def __repr__(self) -> str:
        """
        Detailed representation of the Scout object.

        Returns:
            str: Scout object description
        """
        return f"Scout(features='{self.features}', content_length={len(self.markup)})"

    def _preprocess_markup(self, markup: Union[str, bytes], encoding: Optional[str] = None) -> str:
        """
        Preprocess markup before parsing.

        Args:
            markup (str): Input markup
            encoding (str, optional): Encoding to use

        Returns:
            str: Preprocessed markup
        """
        # Decode markup
        decoded_markup = decode_markup(markup, encoding)

        # Basic HTML cleaning
        # Remove comments, normalize whitespace, etc.
        decoded_markup = re.sub(r"<!--.*?-->", "", decoded_markup, flags=re.DOTALL)
        decoded_markup = re.sub(r"\s+", " ", decoded_markup)

        return decoded_markup

    def wrap(self, wrapper_tag: Tag) -> Tag:
        """Wrap the root tag in another tag with error handling."""
        try:
            return self._soup.wrap(wrapper_tag)
        except Exception:
            return wrapper_tag

    def unwrap(self) -> None:
        """Unwrap the root tag, keeping its contents in the parent, with error handling."""
        try:
            self._soup.unwrap()
        except Exception:
            pass

    def insert_before(self, new_element: Tag) -> None:
        """Insert a tag or string immediately before the root tag with error handling."""
        try:
            self._soup.insert_before(new_element)
        except Exception:
            pass

    def insert_after(self, new_element: Tag) -> None:
        """Insert a tag or string immediately after the root tag with error handling."""
        try:
            self._soup.insert_after(new_element)
        except Exception:
            pass

    def append(self, tag: Tag) -> None:
        """Append a tag to the root tag with error handling."""
        try:
            self._soup.append(tag)
        except Exception:
            pass

    @property
    def descendants(self):
        """Yield all descendants of the root tag in document order."""
        return self._soup.descendants

    @property
    def parents(self):
        """Yield all parents of the root tag up the tree."""
        return self._soup.parents

    @property
    def next_element(self):
        """Return the next element in document order after the root tag."""
        return self._soup.next_element

    @property
    def previous_element(self):
        """Return the previous element in document order before the root tag."""
        return self._soup.previous_element

    def fetch_and_parse(self, url: str, session=None, **kwargs) -> "Scout":
        """Fetch HTML from a URL and parse it with Scout. Prefers curl_cffi."""
        try:
            from curl_cffi import requests as curleq

            s = session or curleq.Session()
            resp = s.get(url, **kwargs)
            return Scout(resp.content, features=self.features)
        except ImportError:
            import requests

            s = session or requests.Session()
            resp = s.get(url, **kwargs)
            return Scout(resp.content, features=self.features)

    def tables_to_dataframe(self, table_index=0, pandas_module=None):
        """Convert the nth table in the document to a pandas DataFrame."""
        try:
            if pandas_module:
                pd = pandas_module
            else:
                import pandas as pd  # type: ignore
        except ImportError:
            raise ImportError("pandas is required for tables_to_dataframe. Please install pandas.")
        tables = self.find_all("table")
        if not tables or table_index >= len(tables):
            return None
        table = tables[table_index]
        rows = table.find_all("tr")
        data = [[cell.get_text(strip=True) for cell in row.find_all(["td", "th"])] for row in rows]
        return pd.DataFrame(data)
