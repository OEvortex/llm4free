import sys
from typing import Any, Dict, List, Optional, Type, Union

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .search import (
    BaseSearch,
    BaseSearchEngine,
    BingSearch,
    BraveSearch,
    DuckDuckGoSearch,
    Mojeek,
    Parallel,
    SerpBase,
    Wikipedia,
    YahooSearch,
)
from .swiftcli import CLI, option
from .version import __version__

console = Console()

# Engine mapping
ENGINES: Dict[str, Union[Type[BaseSearch], Type[BaseSearchEngine]]] = {
    "ddg": DuckDuckGoSearch,
    "duckduckgo": DuckDuckGoSearch,
    "bing": BingSearch,
    "yahoo": YahooSearch,
    "brave": BraveSearch,
    "mojeek": Mojeek,
    "parallel": Parallel,
    "wikipedia": Wikipedia,
    "serpbase": SerpBase,
}


def _get_engine(name: str) -> Union[BaseSearch, BaseSearchEngine]:
    cls: type[BaseSearch | BaseSearchEngine] | None = ENGINES.get(name.lower())
    if not cls:
        rprint(f"[bold red]Error: Engine '{name}' not supported.[/bold red]")
        rprint(f"Available engines: {', '.join(sorted(set(e for e in ENGINES.keys())))}")
        sys.exit(1)
    if not callable(cls):
        rprint(f"[bold red]Error: Engine '{name}' is not callable.[/bold red]")
        sys.exit(1)
    # Explicitly assert cls is not None after the check
    assert cls is not None
    return cls()


def _format_views(count: int) -> str:
    """Format view count to human readable format."""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    elif count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate text to max length."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _print_videos(data: List[Any], title: str) -> None:
    """Print video results in a beautiful format."""
    if not data:
        rprint("[bold yellow]No video results found.[/bold yellow]")
        return

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    for i, video in enumerate(data, 1):
        # Handle both dict and dataclass objects
        if hasattr(video, "title"):
            v_title = video.title
            v_url = video.url
            v_duration = video.duration
            v_uploader = getattr(video, "uploader", "") or getattr(video, "publisher", "")
            v_provider = getattr(video, "provider", "")
            v_published = getattr(video, "published", "")
            v_stats = getattr(video, "statistics", {}) or {}
            v_views = v_stats.get("views", 0) if isinstance(v_stats, dict) else 0
        else:
            v_title = video.get("title", "")
            v_url = video.get("url", "")
            v_duration = video.get("duration", "")
            v_uploader = video.get("uploader", "") or video.get("publisher", "")
            v_provider = video.get("provider", "")
            v_published = video.get("published", "")
            v_stats = video.get("statistics", {}) or {}
            v_views = v_stats.get("views", 0) if isinstance(v_stats, dict) else 0

        # Build video info panel
        info_lines = []
        info_lines.append(f"[bold white]{v_title}[/bold white]")

        meta_parts = []
        if v_duration:
            meta_parts.append(f"[cyan]⏱ {v_duration}[/cyan]")
        if v_views:
            meta_parts.append(f"[green]👁 {_format_views(v_views)} views[/green]")
        if v_published:
            meta_parts.append(f"[dim]{v_published}[/dim]")
        if meta_parts:
            info_lines.append(" • ".join(meta_parts))

        if v_uploader:
            info_lines.append(f"[yellow]📺 {v_uploader}[/yellow]")
        if v_provider and v_provider.lower() != v_uploader.lower():
            info_lines.append(f"[dim]via {v_provider}[/dim]")
        info_lines.append(f"[blue underline]{v_url}[/blue underline]")

        panel = Panel(
            "\n".join(info_lines),
            title=f"[bold magenta]#{i}[/bold magenta]",
            title_align="left",
            border_style="dim",
        )
        console.print(panel)


def _print_news(data: List[Any], title: str) -> None:
    """Print news results in a beautiful format."""
    if not data:
        rprint("[bold yellow]No news results found.[/bold yellow]")
        return

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    for i, article in enumerate(data, 1):
        # Handle both dict and dataclass objects
        if hasattr(article, "title"):
            n_title = article.title
            n_url = article.url
            n_source = getattr(article, "source", "")
            n_date = getattr(article, "date", "")
            n_body = getattr(article, "body", "")
        else:
            n_title = article.get("title", "")
            n_url = article.get("url", "")
            n_source = article.get("source", "")
            n_date = article.get("date", "")
            n_body = article.get("body", "")

        # Build news info panel
        info_lines = []
        info_lines.append(f"[bold white]{n_title}[/bold white]")

        meta_parts = []
        if n_source:
            meta_parts.append(f"[yellow]📰 {n_source}[/yellow]")
        if n_date:
            meta_parts.append(f"[dim]🕐 {n_date}[/dim]")
        if meta_parts:
            info_lines.append(" • ".join(meta_parts))

        if n_body:
            info_lines.append(f"[dim italic]{_truncate(n_body, 150)}[/dim italic]")
        info_lines.append(f"[blue underline]{n_url}[/blue underline]")

        panel = Panel(
            "\n".join(info_lines),
            title=f"[bold magenta]#{i}[/bold magenta]",
            title_align="left",
            border_style="dim",
        )
        console.print(panel)


def _print_suggestions(data: List[Any], title: str) -> None:
    """Print suggestions in a beautiful format."""
    if not data:
        rprint("[bold yellow]No suggestions found.[/bold yellow]")
        return

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Suggestion", style="bold white")
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Description", style="dim")

    for i, item in enumerate(data, 1):
        # Handle different formats
        if isinstance(item, str):
            table.add_row(str(i), item, "", "")
        elif hasattr(item, "query"):
            # Dataclass (SuggestionResult)
            query = item.query
            is_entity = getattr(item, "is_entity", False)
            name = getattr(item, "name", "")
            desc = getattr(item, "desc", "")
            type_str = "[green]Entity[/green]" if is_entity else ""
            display = name if name else query
            table.add_row(str(i), display, type_str, _truncate(desc, 50))
        elif isinstance(item, dict):
            query = item.get("query", item.get("suggestion", str(item)))
            is_entity = item.get("is_entity", "False")
            name = item.get("name", "")
            desc = item.get("desc", "")
            type_str = "[green]Entity[/green]" if is_entity in (True, "True") else ""
            display = name if name else query
            table.add_row(str(i), display, type_str, _truncate(desc, 50))
        else:
            table.add_row(str(i), str(item), "", "")

    console.print(table)
    console.print()


def _print_images(data: List[Any], title: str) -> None:
    """Print image results in a beautiful format."""
    if not data:
        rprint("[bold yellow]No image results found.[/bold yellow]")
        return

    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")

    for i, img in enumerate(data, 1):
        # Handle both dict and dataclass objects
        if hasattr(img, "title"):
            i_title = img.title or "Untitled"
            i_url = getattr(img, "url", "")
            i_source = getattr(img, "source", "")
            i_width = getattr(img, "width", "")
            i_height = getattr(img, "height", "")
        else:
            i_title = img.get("title", "Untitled")
            i_url = img.get("url", "")
            i_source = img.get("source", "")
            i_width = img.get("width", "")
            i_height = img.get("height", "")

        info_lines = []
        info_lines.append(f"[bold white]{_truncate(i_title, 70)}[/bold white]")

        meta_parts = []
        if i_width and i_height:
            meta_parts.append(f"[cyan]{i_width}x{i_height}[/cyan]")
        if i_source:
            meta_parts.append(f"[yellow]{i_source}[/yellow]")
        if meta_parts:
            info_lines.append(" • ".join(meta_parts))

        if i_url:
            info_lines.append(f"[blue underline]{_truncate(i_url, 80)}[/blue underline]")

        panel = Panel(
            "\n".join(info_lines),
            title=f"[bold magenta]#{i}[/bold magenta]",
            title_align="left",
            border_style="dim",
        )
        console.print(panel)


def _print_data(data: Any, title: str = "Search Results") -> None:
    """Prints data in a beautiful table."""
    if not data:
        rprint("[bold yellow]No results found.[/bold yellow]")
        return

    table = Table(title=title, show_header=True, header_style="bold magenta", show_lines=True)

    if isinstance(data, list) and len(data) > 0:
        first_item = data[0]

        # Handle dataclass objects by converting to dict
        if hasattr(first_item, "__dataclass_fields__"):
            # Convert dataclass to dict for each item
            data = [
                {k: getattr(item, k, "") for k in first_item.__dataclass_fields__} for item in data
            ]
            first_item = data[0]

        if isinstance(first_item, dict):
            # Filter out empty or less useful keys for cleaner display
            all_keys = list(first_item.keys())
            # Prioritize important keys
            priority_keys = ["title", "url", "body", "description", "source", "date"]
            keys = [k for k in priority_keys if k in all_keys]
            keys += [k for k in all_keys if k not in keys]

            table.add_column("#", style="dim", width=4)
            for key in keys:
                table.add_column(key.capitalize())

            for i, item in enumerate(data, 1):
                row = [str(i)]
                for key in keys:
                    val = item.get(key, "")
                    if key in ("body", "description") and val and len(str(val)) > 150:
                        val = str(val)[:147] + "..."
                    elif key == "url" and val and len(str(val)) > 60:
                        val = str(val)[:57] + "..."
                    row.append(str(val) if val else "")
                table.add_row(*row)
        else:
            table.add_column("#", style="dim", width=4)
            table.add_column("Result")
            for i, item in enumerate(data, 1):
                table.add_row(str(i), str(item))
    else:
        rprint(f"[bold blue]Result:[/bold blue] {data}")
        return

    console.print(table)


def _print_weather(data: Dict[str, Any]) -> None:
    """Prints weather data in a clean panel."""
    # Be defensive when reading weather payloads
    current = data.get("current") or {}
    location = data.get("location", "Unknown")

    temp = current.get("temperature_c", "N/A")
    feels_like = current.get("feels_like_c", "N/A")
    condition = current.get("condition", "N/A")
    humidity = current.get("humidity", "N/A")
    wind_speed = current.get("wind_speed_ms", "N/A")
    wind_dir = current.get("wind_direction", "N/A")

    weather_info = (
        f"[bold blue]Location:[/bold blue] {location}\n"
        f"[bold blue]Temperature:[/bold blue] {temp}°C (Feels like {feels_like}°C)\n"
        f"[bold blue]Condition:[/bold blue] {condition}\n"
        f"[bold blue]Humidity:[/bold blue] {humidity}%\n"
        f"[bold blue]Wind:[/bold blue] {wind_speed} m/s {wind_dir}°"
    )

    panel = Panel(weather_info, title="Current Weather", border_style="green")
    console.print(panel)

    if isinstance(data.get("daily_forecast"), list):
        forecast_table = Table(title="5-Day Forecast", show_header=True, header_style="bold cyan")
        forecast_table.add_column("Date")
        forecast_table.add_column("Condition")
        forecast_table.add_column("High")
        forecast_table.add_column("Low")

        for day in data.get("daily_forecast", [])[:5]:
            date = day.get("date", "N/A")
            condition = day.get("condition", "N/A")
            max_temp = day.get("max_temp_c")
            min_temp = day.get("min_temp_c")
            max_temp_str = (
                f"{max_temp:.1f}°C" if isinstance(max_temp, (int, float)) else str(max_temp)
            )
            min_temp_str = (
                f"{min_temp:.1f}°C" if isinstance(min_temp, (int, float)) else str(min_temp)
            )
            forecast_table.add_row(date, condition, max_temp_str, min_temp_str)
        console.print(forecast_table)


app: CLI = CLI(name="llm4free", help="Search the web with a simple UI", version=__version__)


@app.command()
def version() -> None:
    """Show the version of llm4free."""
    rprint(f"[bold cyan]llm4free version:[/bold cyan] {__version__}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine (ddg, bing, yahoo, brave, etc.)", default="ddg")
@option("--region", "-r", help="Region for search results", default=None)
@option("--safesearch", "-s", help="SafeSearch setting", default="moderate")
@option("--timelimit", "-t", help="Time limit for results", default=None)
@option("--max-results", "-m", help="Maximum number of results", type=int, default=10)
def text(
    keywords: str,
    engine: str,
    region: Optional[str] = None,
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
) -> None:
    """Perform a text search."""
    try:
        search_engine = _get_engine(engine)
        # Handle region defaults if not provided
        if region is None:
            region = "wt-wt" if engine.lower() in ["ddg", "duckduckgo"] else "us"

        # Most engines use .text(), some use .search() or .run()
        text_method = getattr(search_engine, "text", None)
        if text_method and callable(text_method):
            results = text_method(
                keywords, region=region, safesearch=safesearch, max_results=max_results
            )
        else:
            run_method = getattr(search_engine, "run", None)
            if run_method and callable(run_method):
                results = run_method(
                    keywords, region=region, safesearch=safesearch, max_results=max_results
                )
            else:
                search_method = getattr(search_engine, "search", None)
                if search_method and callable(search_method):
                    results = search_method(keywords, max_results=max_results)
                else:
                    rprint("[bold red]Error: This engine does not support text search.[/bold red]")
                    return

        _print_data(results, title=f"{engine.upper()} Text Search: {keywords}")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine (ddg, bing, yahoo, brave)", default="ddg")
@option("--max-results", "-m", help="Maximum number of results", type=int, default=10)
def images(keywords: str, engine: str, max_results: int) -> None:
    """Perform an images search."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "images", None)
        if method and callable(method):
            results = method(keywords, max_results=max_results)
            _print_images(results, title=f"{engine.upper()} Image Search: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support image search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine (ddg, yahoo, brave)", default="ddg")
@option("--max-results", "-m", help="Maximum number of results", type=int, default=10)
def videos(keywords: str, engine: str, max_results: int) -> None:
    """Perform a videos search."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "videos", None)
        if method and callable(method):
            results = method(keywords, max_results=max_results)
            _print_videos(results, title=f"{engine.upper()} Video Search: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support video search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine (ddg, bing, yahoo, brave)", default="ddg")
@option("--max-results", "-m", help="Maximum number of results", type=int, default=10)
def news(keywords: str, engine: str, max_results: int) -> None:
    """Perform a news search."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "news", None)
        if method and callable(method):
            results = method(keywords, max_results=max_results)
            _print_news(results, title=f"{engine.upper()} News Search: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support news search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--location", "-l", help="Location to get weather for", required=True)
@option("--engine", "-e", help="Search engine (ddg, yahoo)", default="ddg")
def weather(location: str, engine: str) -> None:
    """Get weather information."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "weather", None)
        if method and callable(method):
            results = method(location)
            _print_weather(results)
        else:
            rprint("[bold red]Error: This engine does not support weather search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine (ddg, yahoo)", default="ddg")
def answers(keywords: str, engine: str) -> None:
    """Perform an answers search."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "answers", None)
        if method and callable(method):
            results = method(keywords)
            _print_data(results, title=f"{engine.upper()} Answers: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support answers search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--query", "-q", help="Search query", required=True)
@option("--engine", "-e", help="Search engine (ddg, bing, yahoo, yep, brave)", default="ddg")
def suggestions(query: str, engine: str) -> None:
    """Get search suggestions."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "suggestions", None)
        if method and callable(method):
            results = method(query)
            _print_suggestions(results, title=f"{engine.upper()} Suggestions: {query}")
        else:
            rprint("[bold red]Error: This engine does not support suggestions.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Text for translation", required=True)
@option("--from-lang", "-f", help="Language to translate from", default=None)
@option("--to", "-t", help="Language to translate to", default="en")
@option("--engine", "-e", help="Search engine (ddg, yahoo)", default="ddg")
def translate(
    keywords: str, from_lang: Optional[str] = None, to: str = "en", engine: str = "ddg"
) -> None:
    """Perform translation."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "translate", None)
        if method and callable(method):
            results = method(keywords, from_lang=from_lang, to_lang=to)
            _print_data(results, title=f"{engine.upper()} Translation: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support translation.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--place", "-p", help="Place name")
@option("--radius", "-r", help="Search radius (km)", type=int, default=0)
@option("--engine", "-e", help="Search engine (ddg, yahoo)", default="ddg")
def maps(keywords: str, place: Optional[str] = None, radius: int = 0, engine: str = "ddg") -> None:
    """Perform a maps search."""
    try:
        search_engine = _get_engine(engine)
        method = getattr(search_engine, "maps", None)
        if method and callable(method):
            results = method(keywords, place=place, radius=radius)
            _print_data(results, title=f"{engine.upper()} Maps Search: {keywords}")
        else:
            rprint("[bold red]Error: This engine does not support maps search.[/bold red]")
    except Exception as e:
        rprint(f"[bold red]Error:[/bold red] {str(e)}")


# Keep search for compatibility/convenience
@app.command()
@option("--keywords", "-k", help="Search keywords", required=True)
@option("--engine", "-e", help="Search engine", default="ddg")
@option("--max-results", "-m", help="Maximum results", type=int, default=10)
def search(keywords: str, engine: str, max_results: int) -> None:
    """Unified search command across all engines."""
    # Call the local `text` function implementation (not a command object)
    text(keywords=keywords, engine=engine, max_results=max_results)


def main():
    """Main entry point for the CLI."""
    try:
        app.run()
    except Exception as e:
        rprint(f"[bold red]CLI Error:[/bold red] {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
