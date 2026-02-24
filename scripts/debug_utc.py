from app.services.fetchers.youtube import search_videos, fetch_comments

def debug_utc():
    queries = [
        "University Town Center Irvine apartments review",
        "UTC Irvine living",
        "Irvine Company Apartments University Town Center",
        "Living in Irvine California vlog"  # A very broad one to ensure SOMETHING works if others fail
    ]

    for query in queries:
        print(f"\n--- Testing Query: '{query}' ---")
        
        video_ids = search_videos(query, max_results=3)
        print(f"Found video IDs: {video_ids}")
        
        if not video_ids:
            print("No videos found.")
            continue

        total_comments_for_query = 0
        for vid in video_ids:
            print(f"  Fetching comments for video {vid}...")
            comments = fetch_comments(vid, max_results=5)
            count = len(comments)
            print(f"    - Found {count} comments")
            total_comments_for_query += count
            
            if comments:
                print(f"    - Sample: {comments[0][:60]}...")
        
        if total_comments_for_query > 0:
            print(f"SUCCESS: Found {total_comments_for_query} total comments with query '{query}'")
            # We could break here if we just want to find the first working one
            # break 
        else:
            print(f"FAILURE: No comments found for query '{query}'")

if __name__ == "__main__":
    debug_utc()
