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


def fetch_comments(video_id: str, max_results: int = 20) -> list[dict]:
    """
    Fetches top-level comments and their replies for a given video ID.
    Returns a list of dictionaries containing structured comment data.
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
                "part": "snippet,replies",
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
                    # Top-level comment
                    top_level = item["snippet"]["topLevelComment"]
                    snippet = top_level["snippet"]
                    
                    comment_data = {
                        "id": top_level["id"],
                        "text": snippet["textDisplay"],
                        "author": snippet.get("authorDisplayName", "Unknown"),
                        "like_count": snippet.get("likeCount", 0),
                        "published_at": snippet.get("publishedAt"),
                        "parent_id": None, # It's a top-level comment
                        "video_id": video_id
                    }
                    all_comments.append(comment_data)
                    
                    # Fetch replies if they exist in the response
                    if "replies" in item:
                        for reply in item["replies"]["comments"]:
                            reply_snippet = reply["snippet"]
                            reply_data = {
                                "id": reply["id"],
                                "text": reply_snippet["textDisplay"],
                                "author": reply_snippet.get("authorDisplayName", "Unknown"),
                                "like_count": reply_snippet.get("likeCount", 0),
                                "published_at": reply_snippet.get("publishedAt"),
                                "parent_id": top_level["id"], # Link to parent
                                "video_id": video_id
                            }
                            all_comments.append(reply_data)
                            
                    if len(all_comments) >= max_results:
                        break
                
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
                    
        return all_comments
            
    except (HTTPError, URLError, OSError) as e:
        print(f"Failed to fetch comments for video {video_id}: {e}")
        return all_comments
