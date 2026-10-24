<div align="center">
  <a href="https://github.com/OEvortex/llm4free">
    <img src="https://img.shields.io/badge/YTToolkit-YouTube%20Toolkit-red?style=for-the-badge&logo=youtube&logoColor=white" alt="YTToolkit Logo">
  </a>
  <h1>YTToolkit</h1>
  <p><strong>YouTube downloading, transcription, and data extraction</strong></p>

  <p>
    <a href="https://pypi.org/project/llm4free/"><img src="https://img.shields.io/pypi/v/llm4free.svg?style=flat-square&logo=pypi&label=PyPI" alt="PyPI Version"></a>
    <a href="#"><img src="https://img.shields.io/badge/No%20API%20Key-Required-success?style=flat-square" alt="No API Key Required"></a>
    <a href="#"><img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python Version"></a>
  </p>
</div>

> [!NOTE]
> YTToolkit provides YouTube downloading, transcript extraction, and data retrieval
> without an official API key.

## ✨ Features

- **Video downloading** — MP4/MP3 output, quality/resolver selection, directory and filename control
- **Transcripts** — InnerTube-based fetching, language selection, optional formatting preservation
- **Channel/video/playlist data** — metadata, uploads, streams, chapters, related videos, comments
- **Search and discovery** — videos, channels, playlists, Shorts, live streams, filters, trending
- **Captions** — available languages, timed/plain transcripts, transcript search

## 🚀 Installation

```bash
pip install -U llm4free
```

## 💻 Quick Start

### Video downloading

`Handler` takes only the query and options that affect discovery. Format,
quality, and limit are arguments to `run()` or `auto_save()`.

```python
from llm4free import Handler

# Download the best match with default format (mp4) and quality ("auto")
downloader = Handler("https://youtube.com/watch?v=dQw4w9WgXcQ")
downloader.auto_save(dir="./downloads")

# Extract audio
Handler("https://youtube.com/watch?v=dQw4w9WgXcQ").auto_save(
    dir="./downloads",
    format="mp3",
    quality="128kbps",
)

# Download the first 5 results for a search query
Handler("python tutorial").auto_save(
    dir="./downloads",
    format="mp4",
    quality="720p",
    limit=5,
)
```

`auto_save()` forwards extra keyword arguments to `run()`. To save a single
streamed result yourself, use `run()` and `save()`:

```python
from llm4free import Handler

handler = Handler("python tutorial")
for item in handler.run(format="mp4", quality="720p", limit=3):
    handler.save(item, dir="./downloads")
```

Available `Handler` constructor arguments: `query`, `author`, `timeout`,
`confirm`, `unique`, `thread`. `run()` accepts `format`, `quality`, `resolver`,
`limit`, `keyword`, and `author`. `save()` accepts a `third_dict` produced by
`run()`, plus `dir`, `progress_bar`, `quiet`, `naming_format`, `chunk_size`,
`play`, `resume`, and `disable_history`.

Download history is stored globally and can be read with
`llm4free.Extra.YTToolkit.YTdownloader.utils.get_history()`.

### Transcript extraction

```python
from llm4free import YTTranscriber

transcript = YTTranscriber.get_transcript("https://youtube.com/watch?v=dQw4w9WgXcQ")
for entry in transcript[:5]:
    print(f"[{entry['start']:.1f}s] {entry['text']}")

# Language selection; None means the first available transcript
spanish = YTTranscriber.get_transcript("dQw4w9WgXcQ", languages="es")
any_transcript = YTTranscriber.get_transcript("dQw4w9WgXcQ", languages=None)

# Proxies and formatting
transcript = YTTranscriber.get_transcript(
    "dQw4w9WgXcQ",
    proxies={"http": "http://proxy:8080"},
    preserve_formatting=True,
)
```

`get_transcript()` also accepts `cookies` (path to a cookie file) and is cached
with `lru_cache(maxsize=100)`.

### Channel information

```python
from llm4free import Channel

channel = Channel("@PewDiePie")  # handle, channel ID, custom URL, or user URL

print(channel.name, channel.subscribers, channel.views, channel.country)
print(channel.avatar, channel.banner)

recent_videos = channel.uploads(10)  # list of video IDs
if channel.live:
    print("Streaming:", channel.streaming_now)
print(channel.playlists)
```

Metadata keys include `id`, `name`, `url`, `description`, `country`,
`custom_url`, `subscribers`, `views`, `created_at`, `video_count`, `avatar`,
`banner`, `verified`, and `socials`. They are also exposed as attributes.

### Video metadata

```python
from llm4free import Video

video = Video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
metadata = video.metadata

print(metadata["title"], metadata["views"], metadata["duration"], metadata["upload_date"])
print(video.is_live, video.is_short, video.hashtags)

related = video.get_related_videos(5)      # video IDs
chapters = video.get_chapters()            # [{title, start_time, start_seconds}, ...] or None

for comment in video.stream_comments(limit=10):
    print(comment["author"], comment["text"])

print(video.thumbnail_urls["default"], video.thumbnail_urls["maxres"])
print(video.embed_html, video.embed_url)
```

`stream_comments()` reads comments embedded in the initial page load and may
return nothing for videos whose comments are loaded dynamically.

### Search and trending

All search helpers return lists of IDs (video/channel/playlist), not objects.

```python
from llm4free import Search, Extras

video_ids = Search.videos("Python tutorial", limit=5)
channel_ids = Search.channels("coding", limit=3)
playlist_ids = Search.playlists("music mix", limit=3)

shorts = Search.shorts("funny cats", limit=5)
live = Search.live_streams("gaming", limit=5)
long_videos = Search.videos_by_duration("tutorial", duration="long")
recent = Search.videos_by_upload_date("news", when="today")

trending = Extras.trending_videos(limit=10)
music_videos = Extras.music_videos(limit=5)
gaming_videos = Extras.gaming_videos(limit=5)
shorts_videos = Extras.shorts_videos(limit=5)
```

`videos_by_duration()` accepts `"short"`, `"medium"`, or `"long"`.
`videos_by_upload_date()` accepts `"hour"`, `"today"`, `"week"`, `"month"`,
or `"year"`.

### Captions API

```python
from llm4free.Extra.YTToolkit.ytapi import Captions

languages = Captions.get_available_languages("dQw4w9WgXcQ")
for lang in languages:
    print(f"{lang['code']}: {lang['name']} (auto: {lang['is_auto']})")

timed = Captions.get_timed_transcript("dQw4w9WgXcQ", language="en")
for entry in timed[:3]:
    print(f"[{entry['start']:.1f}s] {entry['text']}")

text = Captions.get_transcript("dQw4w9WgXcQ")
print(text[:200])

matches = Captions.search_transcript("dQw4w9WgXcQ", "never gonna")
for match in matches:
    print(f"{match['start']:.1f}s: {match['text']}")
```

## 📚 Module Structure

| Module | File | Description |
|--------|------|-------------|
| Video downloader | [`YTdownloader.py`](YTdownloader.py) | `Handler` for downloading/search |
| Transcript retriever | [`transcriber.py`](transcriber.py) | `YTTranscriber` (InnerTube) |
| Channel data | [`ytapi/channel.py`](ytapi/channel.py) | `Channel` metadata and uploads |
| Video information | [`ytapi/video.py`](ytapi/video.py) | `Video` metadata and helpers |
| Search | [`ytapi/query.py`](ytapi/query.py) | `Search` |
| Trending/categories | [`ytapi/extras.py`](ytapi/extras.py) | `Extras` |
| Playlists | [`ytapi/playlist.py`](ytapi/playlist.py) | `Playlist` |
| Captions | [`ytapi/captions.py`](ytapi/captions.py) | `Captions` |
| Suggestions | [`ytapi/suggestions.py`](ytapi/suggestions.py) | `Suggestions` |
| Shorts | [`ytapi/shorts.py`](ytapi/shorts.py) | `Shorts` |
| Hashtags | [`ytapi/hashtag.py`](ytapi/hashtag.py) | `Hashtag` |

See [`ytapi/README.md`](ytapi/README.md) for the data-extraction API.

## ⚠️ Disclaimer

> [!WARNING]
> Use this toolkit responsibly and in accordance with YouTube's terms of service.
> The developers are not responsible for misuse.

> [!IMPORTANT]
> Web scraping is fragile. YouTube may change its site or APIs at any time, which
> can break functionality.

## 🤝 Contributing

Contributions are welcome — please open a pull request.

<div align="center">
  <p>
    <a href="https://t.me/OEvortexAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
    <a href="https://youtube.com/@OEvortex"><img alt="YouTube" src="https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
    <a href="https://buymeacoffee.com/oevortex"><img alt="Buy Me A Coffee" src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black"></a>
  </p>
</div>
