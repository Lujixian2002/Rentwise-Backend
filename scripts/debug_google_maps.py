import sys
import os

# Add the project root to sys.path so we can import from 'app'
sys.path.append(os.getcwd())

from app.services.fetchers.google_maps import fetch_commute_minutes, fetch_google_reviews

def debug_fetch_commute(origin_lat=33.6500, origin_lng=-117.7400, dest_lat=33.6405, dest_lng=-117.8443):
    print(f"\n--- Debugging Google Maps Commute Fetcher ---")
    
    origin = (origin_lat, origin_lng)
    destination = (dest_lat, dest_lng)
    
    print(f"Origin: {origin}")
    print(f"Destination: {destination}")
    
    print("\nFetching commute minutes (driving)...")
    minutes = fetch_commute_minutes(origin, destination, mode="driving")
    
    if minutes is not None:
        print(f"Success! Estimated commute time: {minutes} minutes.")
    else:
        print("Failed to fetch commute time. Check your API key or network connection.")

def debug_fetch_reviews(keyword="UC Irvine"):
    print(f"\n--- Debugging Google Maps Reviews Fetcher ---")
    print(f"Searching for: '{keyword}'")
    
    reviews = fetch_google_reviews(keyword)
    
    if reviews:
        print(f"Success! Found {len(reviews)} reviews.")
        print("Sample review:")
        print(f"Author: {reviews[0].get('author_name')}")
        print(f"Rating: {reviews[0].get('rating')}")
        print(f"Text: {reviews[0].get('text')[:100]}...")
    else:
        print("Failed to fetch reviews or no reviews found. Check your API key or network connection.")

if __name__ == "__main__":
    # Default test: Irvine Spectrum to UCI
    debug_fetch_commute()
    debug_fetch_reviews()
