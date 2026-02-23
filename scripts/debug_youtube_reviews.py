import sys
import os

# Add the project root to sys.path so we can import from 'app'
sys.path.append(os.getcwd())

from app.db.database import SessionLocal
from app.db import crud
from app.services.ingest_service import ensure_reviews_fresh
from app.services.fetchers.youtube import search_video, fetch_comments
from app.schemas.community import ReviewResponse

def debug_fetch_reviews(community_id="irvine-spectrum"):
    print(f"\n--- Debugging Reviews for '{community_id}' ---")
    
    db = SessionLocal()
    try:
        # 1. Check if community exists
        community = crud.get_community(db, community_id)
        if not community:
            print(f"ERROR: Community '{community_id}' not found in DB.")
            return

        print(f"Found Community: {community.name} ({community.city}, {community.state})")
        
        # 2. Check existing metrics for video ID
        metrics = crud.get_metrics(db, community_id)
        video_id = metrics.youtube_video_id if metrics else None
        print(f"Existing Video ID in Metrics: {video_id}")
        
        # 3. Simulate or Run search_video if needed
        if not video_id:
            query = f"{community.name} {community.city or ''} apartment tour"
            print(f"Searching YouTube for: '{query}'")
            found_id = search_video(query)
            print(f"Search Result: {found_id}")
            if found_id:
                # Update metrics manually for test
                crud.upsert_metrics(db, community_id, {"youtube_video_id": found_id})
                video_id = found_id
        
        if not video_id:
            print("ERROR: Could not find a video ID. Cannot fetch comments.")
            return

        # 4. Fetch comments directly to test API
        print(f"Fetching comments for Video ID: {video_id}...")
        raw_comments = fetch_comments(video_id, max_results=5) # fetching 5 just for check
        print(f"Fetched {len(raw_comments)} comments from YouTube API.")
        if raw_comments:
            print(f"Sample Comment: {raw_comments[0]}")
        
        # 5. Run the full ingest service function to test integration
        print("Running 'ensure_reviews_fresh' service function...")
        ensure_reviews_fresh(db, community_id)
        
        # 6. Check DB count
        count = crud.get_reviews_count(db, community_id)
        print(f"Total Reviews in DB for {community_id}: {count}")
        
        # 7. List some
        reviews = crud.get_reviews_by_community(db, community_id, limit=3)
        for r in reviews:
            print(f" - [{r.platform}] {r.posted_at}: {r.body_text[:50]}...")

    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug_fetch_reviews(sys.argv[1])
    else:
        debug_fetch_reviews("irvine-spectrum")
