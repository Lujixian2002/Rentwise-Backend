from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


def search_videos(query: str, max_results: int = 5) -> list[str]:
    """
    Searches YouTube for videos matching the query.
    Returns a list of Video IDs found.
    """
    settings = get_settings()
    if not settings.youtube_api_key:
        return []

    base_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": settings.youtube_api_key,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = Request(url)
        with urlopen(req) as response:
            if response.status != 200:
                return []
            data = json.loads(response.read().decode())
            items = data.get("items", [])
            video_ids = [item["id"]["videoId"] for item in items if "id" in item and "videoId" in item["id"]]
            return video_ids
    except (HTTPError, URLError, OSError):
        return []


def fetch_comments(video_id: str, max_results: int = 20) -> list[str]:
    """
    Fetches top-level comments for a given video ID.
    Supports fetching up to 100 comments via pagination (if max_results set higher).
    """
    settings = get_settings()
    if not settings.youtube_api_key:
        return []

    base_url = "https://www.googleapis.com/youtube/v3/commentThreads"
    all_comments = []
    next_page_token = None
    
    # YouTube API maxResults per page is 100.
    page_size = min(max_results, 100)
    
    try:
        while len(all_comments) < max_results:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": page_size,
                "textFormat": "plainText",
                "key": settings.youtube_api_key,
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            req = Request(url)
            
            with urlopen(req) as response:
                if response.status != 200:
                    print(f"Error fetching comments: HTTP {response.status}")
                    break
                    
                data = json.loads(response.read().decode())
                items = data.get("items", [])
                
                for item in items:
                    comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                    all_comments.append(comment)
                    if len(all_comments) >= max_results:
                        break
                
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
                    
        return all_comments
            
    except (HTTPError, URLError, OSError) as e:
        print(f"Failed to fetch comments for video {video_id}: {e}")
        return all_comments
