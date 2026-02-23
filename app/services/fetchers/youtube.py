from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


def search_video(query: str) -> str | None:
    """
    Searches YouTube for a video matching the query.
    Returns the first Video ID found, or None.
    """
    settings = get_settings()
    if not settings.youtube_api_key:
        return None

    base_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "key": settings.youtube_api_key,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = Request(url)
        with urlopen(req) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode())
            items = data.get("items", [])
            if not items:
                return None
            # Extract video ID from the first result
            video_id = items[0]["id"]["videoId"]
            return video_id
    except (HTTPError, URLError, OSError):
        return None


def fetch_comments(video_id: str, max_results: int = 20) -> list[dict]:
    """
    Fetches top-level comments for a given video ID.
    Returns list of dicts:
    [{'id': str, 'text': str, 'published_at': str}, ... ]
    """
    settings = get_settings()
    if not settings.youtube_api_key:
        return []

    base_url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "textFormat": "plainText",
        "order": "relevance",
        "key": settings.youtube_api_key,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = Request(url)
        with urlopen(req) as response:
            if response.status != 200:
                print(f"Error fetching comments: HTTP {response.status}")
                return []
            data = json.loads(response.read().decode())
            items = data.get("items", [])
            comments = []
            for item in items:
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "id": item["id"],
                    "text": snippet["textDisplay"],
                    "published_at": snippet["publishedAt"]
                })
            return comments
    except (HTTPError, URLError, OSError) as e:
        print(f"Failed to fetch comments for video {video_id}: {e}")
        return []
