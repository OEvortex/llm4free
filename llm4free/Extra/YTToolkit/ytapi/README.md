# 🎬 YTAPI: YouTube Data Extraction Module

## Overview

YTAPI is a powerful, lightweight YouTube data extraction module within the LLM4Free Python package. It provides comprehensive tools for retrieving YouTube video, channel, playlist, and search data without requiring an API key.

## ✨ Features

### Core Classes

- **Video** - Video metadata, comments, chapters, related videos
- **Channel** - Channel info, uploads, streams, playlists
- **Playlist** - Playlist metadata and videos
- **Search** - Search videos, channels, playlists, Shorts, live streams

### Additional Classes

- **Suggestions** - YouTube search autocomplete
- **Shorts** - YouTube Shorts detection and search
- **Hashtag** - Videos by hashtag
- **Captions** - Video transcripts and subtitles
- **Extras** - Trending content by category

> [!NOTE]
> Search and extras helpers return lists of IDs (video, channel, or playlist),
> not objects. Construct `Video`, `Channel`, or `Playlist` with an ID when you
> need metadata.

## 📦 Installation

```bash
pip install llm4free
```

## 💡 Quick Examples

### Video Operations

```python
from llm4free.Extra.YTToolkit.ytapi import Video

video = Video("dQw4w9WgXcQ")

# Get metadata
meta = video.metadata
print(f"Title: {meta['title']}")
print(f"Views: {meta['views']}")

# New features
print(f"Is Live: {video.is_live}")
print(f"Is Short: {video.is_short}")
print(f"Hashtags: {video.hashtags}")

# Get related videos
related = video.get_related_videos(5)
print(f"Related: {related}")

# Get chapters
chapters = video.get_chapters()
if chapters:
    for ch in chapters:
        print(f"{ch['start_time']} - {ch['title']}")

# Stream comments
for comment in video.stream_comments(10):
    print(f"{comment['author']}: {comment['text'][:50]}")
```

### Search Operations

```python
from llm4free.Extra.YTToolkit.ytapi import Search

# Basic search
videos = Search.videos("python tutorial", limit=10)
channels = Search.channels("tech", limit=5)

# New search features
shorts = Search.shorts("funny cats", limit=10)
live = Search.live_streams("music", limit=5)

# Filtered search
recent = Search.videos_by_upload_date("news", when="today", limit=10)
short_vids = Search.videos_by_duration("tutorial", duration="short", limit=10)
```

### Suggestions (NEW)

```python
from llm4free.Extra.YTToolkit.ytapi import Suggestions

# Get autocomplete suggestions
suggestions = Suggestions.autocomplete("how to")
print(suggestions)
# ['how to make money', 'how to tie a tie', ...]

# Get trending searches
trending = Suggestions.trending_searches()
print(trending)
```

### Shorts (NEW)

```python
from llm4free.Extra.YTToolkit.ytapi import Shorts

# Check if a video is a Short
is_short = Shorts.is_short("video_id")

# Get trending Shorts
trending = Shorts.get_trending(10)

# Search for Shorts
results = Shorts.search("dance", limit=20)
```

### Hashtag (NEW)

```python
from llm4free.Extra.YTToolkit.ytapi import Hashtag

# Get videos by hashtag
videos = Hashtag.get_videos("python", limit=20)

# Get hashtag metadata
meta = Hashtag.get_metadata("coding")
print(f"Tag: {meta['tag']}")
print(f"Sample videos: {meta['sample_videos']}")

# Extract hashtags from text
tags = Hashtag.extract_from_text("Check out my #python #tutorial!")
print(tags)  # ['python', 'tutorial']
```

### Captions (NEW)

```python
from llm4free.Extra.YTToolkit.ytapi import Captions

# Get available languages
langs = Captions.get_available_languages("dQw4w9WgXcQ")
for lang in langs:
    print(f"{lang['code']}: {lang['name']}")

# Get transcript
transcript = Captions.get_transcript("dQw4w9WgXcQ", "en")
print(transcript[:500])

# Get timed transcript
timed = Captions.get_timed_transcript("dQw4w9WgXcQ")
for entry in timed[:5]:
    print(f"{entry['start']:.1f}s: {entry['text']}")

# Search within transcript
matches = Captions.search_transcript("dQw4w9WgXcQ", "never gonna")
for match in matches:
    print(f"{match['start']:.1f}s: {match['text']}")
```

### Extras (Trending)

```python
from llm4free.Extra.YTToolkit.ytapi import Extras

# Get trending content
trending = Extras.trending_videos(10)
music = Extras.music_videos(10)
gaming = Extras.gaming_videos(10)
news = Extras.news_videos(10)
live = Extras.live_videos(10)
sports = Extras.sport_videos(10)
educational = Extras.educational_videos(10)

# New categories
shorts = Extras.shorts_videos(10)
movies = Extras.movies(10)
podcasts = Extras.podcasts(10)
```

### Channel Operations

```python
from llm4free.Extra.YTToolkit.ytapi import Channel

channel = Channel("@MrBeast")

# Get metadata
meta = channel.metadata
print(f"Name: {meta['name']}")
print(f"Subscribers: {meta['subscribers']}")

# Get uploads (list of video IDs)
uploads = channel.uploads(20)

# Check if live
if channel.live:
    print(f"Currently streaming: {channel.streaming_now}")

# Get playlists
playlists = channel.playlists
```

### Playlist Operations

```python
from llm4free.Extra.YTToolkit.ytapi import Playlist

playlist = Playlist("PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")

# Get metadata
meta = playlist.metadata
print(f"Name: {meta['name']}")
print(f"Videos: {meta['video_count']}")
print(f"Video IDs: {meta['videos']}")
```

## 🔧 Available Classes

| Class | Methods |
|-------|---------|
| `Video` | `metadata`, `embed_html`, `embed_url`, `thumbnail_url`, `thumbnail_urls`, `is_live`, `is_short`, `hashtags`, `get_related_videos`, `get_chapters`, `stream_comments` |
| `Channel` | `metadata`, `live`, `streaming_now`, `current_streams`, `old_streams`, `uploads`, `last_uploaded`, `upcoming`, `playlists` |
| `Playlist` | `metadata` |
| `Search` | `video`, `videos`, `channel`, `channels`, `playlist`, `playlists`, `shorts`, `live_streams`, `videos_by_duration`, `videos_by_upload_date` |
| `Suggestions` | `autocomplete`, `trending_searches` |
| `Shorts` | `is_short`, `get_trending`, `search` |
| `Hashtag` | `get_videos`, `get_metadata`, `extract_from_text` |
| `Captions` | `get_available_languages`, `get_transcript`, `get_timed_transcript`, `search_transcript` |
| `Extras` | `trending_videos`, `music_videos`, `gaming_videos`, `news_videos`, `live_videos`, `sport_videos`, `educational_videos`, `shorts_videos`, `movies`, `podcasts` |

## ⚠️ Notes

- All features work without a YouTube API key
- Some features may break if YouTube changes their HTML structure
- Rate limiting may apply for excessive requests
