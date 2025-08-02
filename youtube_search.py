import requests
import os
import subprocess
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
SEARCH_QUERY = ["미국 경제", "미국 주식 투자", "미국 부동산"]
MAX_RESULTS = 10

def search_youtube(query):
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",       # Sort by popularity
        "videoEmbeddable": "true",  # Only embeddable videos
        "maxResults": MAX_RESULTS,
        "key": API_KEY
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("items", []):
        video_id = item["id"]["videoId"]
        snippet = item["snippet"]
        results.append({
            "video_id": video_id,
            "title": snippet["title"],
            "thumbnail": snippet["thumbnails"]["high"]["url"],
            "channel": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })
    
    return results

def download_3min_audio(video_url, output_filename):
    command = [
        "yt-dlp",
        "--download-sections", "*00:00:00-00:03:00",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", output_filename,
        video_url,
    ]

    try:
        subprocess.run(command, check=True)
        print(f"✅ Audio saved to {output_filename}")
    except subprocess.CalledProcessError as e:
        print("❌ Failed to download audio:", e)

# Run test
if __name__ == "__main__":
    videos = search_youtube(SEARCH_QUERY)
    if videos:
        video = videos[0]  # 첫 번째 영상만 선택
        print(f"🎥 Top video: {video['title']}")
        audio_filename = f"{video['video_id']}.mp3"
        download_3min_audio(video["url"], output_filename=audio_filename)
    else:
        print("❗ No videos found.")
