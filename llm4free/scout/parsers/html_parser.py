"""
Scout HTML Parser - Advanced HTML Parsing with Python's Built-in Parser
"""

import html.entities as html_entities
import re
from html.parser import HTMLParser as StdHTMLParser
from typing import List

from ..element import NavigableString, Tag


class HTMLParser:
    """
    Advanced HTML parser using Python's built-in HTMLParser.
    Provides robust parsing with enhanced error handling and flexibility.
    """

    def __init__(self):
        """
        Initialize the HTML parser with advanced parsing capabilities.
        """
        self._root = Tag("html")
        self._current_tag = self._root
        self._tag_stack = [self._root]
        self._parsing_errors = []

    def parse(self, markup: str) -> Tag:
        """
        Parse HTML markup and return the root tag.

        Args:
            markup (str): HTML content to parse

        Returns:
            Tag: Parsed HTML document root
        """
        try:
            # Preprocess markup to handle common issues
            markup = self._preprocess_markup(markup)

            # Create a standard HTML parser
            parser = _ScoutHTMLParser(self)
            parser.feed(markup)
            parser.close()

            return self._root
        except Exception as e:
            self._parsing_errors.append(str(e))
            return self._root

    def _preprocess_markup(self, markup: str) -> str:
        """
        Preprocess HTML markup to handle common parsing issues.

        Args:
            markup (str): Raw HTML markup

        Returns:
            str: Preprocessed HTML markup
        """
        # Do not globally html.unescape here: it turns &quot; inside attribute
        # values (e.g. JSON payloads) into raw quotes and breaks tokenization.
        # HTMLParser already unescapes entities in attributes and text.

        # Handle unclosed tags (basic approach)
        markup = re.sub(
            r"<(br|img|input|hr|meta)([^>]*?)(?<!/)>", r"<\1\2 />", markup, flags=re.IGNORECASE
        )

        # Remove comments (optional, can be configurable)
        markup = re.sub(r"<!--.*?-->", "", markup, flags=re.DOTALL)

        return markup

    def add_tag(self, tag: Tag):
        """
        Add a tag to the current parsing context.

        Args:
            tag (Tag): Tag to add
        """
        # Set parent-child relationships
        tag.parent = self._current_tag
        self._current_tag.contents.append(tag)

        # Update current tag if it's an opening tag
        self._current_tag = tag
        self._tag_stack.append(tag)

    def add_text(self, text: str):
        """
        Add text content to the current tag.

        Args:
            text (str): Text content
        """
        if text.strip():
            text_node = NavigableString(text)
            text_node.parent = self._current_tag
            self._current_tag.contents.append(text_node)

    def close_tag(self):
        """
        Close the current tag and return to parent context.
        """
        if len(self._tag_stack) > 1:
            self._tag_stack.pop()
            self._current_tag = self._tag_stack[-1]

    def get_parsing_errors(self) -> List[str]:
        """
        Retrieve parsing errors encountered during HTML processing.

        Returns:
            List[str]: List of parsing error messages
        """
        return self._parsing_errors


class _ScoutHTMLParser(StdHTMLParser):
    """
    Internal HTML parser that integrates with Scout's parsing mechanism.
    """

    def __init__(self, scout_parser: HTMLParser):
        """
        Initialize the parser with a Scout HTML parser.

        Args:
            scout_parser (HTMLParser): Scout's HTML parser instance
        """
        super().__init__(convert_charrefs=True)
        self._scout_parser = scout_parser

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        """
        Handle opening tags during parsing.

        Args:
            tag (str): Tag name
            attrs (List[tuple]): Tag attributes
        """
        # Convert attrs to dictionary
        attrs_dict = dict(attrs)

        # Create Tag instance
        new_tag = Tag(tag, attrs_dict)

        # Add tag to the parsing context
        self._scout_parser.add_tag(new_tag)

    def handle_endtag(self, tag: str):
        """
        Handle closing tags during parsing.

        Args:
            tag (str): Tag name
        """
        # Close the current tag
        self._scout_parser.close_tag()

    def handle_data(self, data: str):
        """
        Handle text data during parsing.

        Args:
            data (str): Text content
        """
        # Add text to the current tag
        self._scout_parser.add_text(data)

    def handle_comment(self, data: str):
        """
        Handle HTML comments (optional, can be configured).

        Args:
            data (str): Comment content
        """
        # Optionally handle comments
        comment_tag = Tag("comment")
        comment_tag.attrs["content"] = data
        self._scout_parser.add_tag(comment_tag)

    def handle_decl(self, decl: str):
        """
        Handle HTML declarations.

        Args:
            decl (str): Declaration content
        """
        # Create a special tag for declarations
        decl_tag = Tag("!DOCTYPE")
        decl_tag.attrs["content"] = decl
        self._scout_parser.add_tag(decl_tag)

    def handle_pi(self, data: str):
        """
        Handle processing instructions.

        Args:
            data (str): Processing instruction content
        """
        # Create a special tag for processing instructions
        pi_tag = Tag("?")
        pi_tag.attrs["content"] = data
        self._scout_parser.add_tag(pi_tag)

    def handle_entityref(self, name: str):
        """
        Handle HTML entity references.

        Args:
            name (str): Entity reference name
        """
        # Convert entity references to their actual characters
        char = html_entities.html5.get(name, f"&{name};")
        self._scout_parser.add_text(char)

    def handle_charref(self, name: str):
        """
        Handle character references.

        Args:
            name (str): Character reference name
        """
        # Convert character references to their actual characters
        try:
            if name.startswith("x"):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self._scout_parser.add_text(char)
        except ValueError:
            # Fallback for invalid references
            self._scout_parser.add_text(f"&#{name};")

    def close(self):
        """
        Finalize parsing and perform cleanup.
        """
        super().close()
