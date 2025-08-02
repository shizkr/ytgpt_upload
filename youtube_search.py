import openai
import requests
import os
import isodate
import subprocess
from dotenv import load_dotenv
from supabase import create_client, Client
from topic_selector import get_random_topic

# Load API key from .env file
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
MAX_RESULTS = 10

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
topic = get_random_topic()  # Get a random topic from the topic selector
SEARCH_QUERY = [topic["keyword"]]
print(f"📅 Selected topic: {topic['board_type']} - {topic['keyword']}")

def parse_duration_to_minutes(duration_str):
    duration = isodate.parse_duration(duration_str)
    return duration.total_seconds() / 60

def filter_by_duration(video_ids, max_minutes=10):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "contentDetails,snippet",
        "id": ",".join(video_ids),
        "key": API_KEY
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    filtered = []
    for item in data["items"]:
        minutes = parse_duration_to_minutes(item["contentDetails"]["duration"])
        if minutes <= max_minutes:
            filtered.append({
                "video_id": item["id"],
                "title": item["snippet"]["title"],
                "thumbnail": item["snippet"]["thumbnails"]["high"]["url"],
                "channel": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "description": item["snippet"]["description"],
                "duration": minutes,
                "url": f"https://www.youtube.com/watch?v={item['id']}"
            })
    return filtered

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

    if not data.get("items"):
        print("❗ No videos found for the query.")
        return []

    video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
    return filter_by_duration(video_ids, max_minutes=50)

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

def transcribe_audio(audio_path: str) -> str:
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko"  # 한국어 인식
        )
    return transcript.text

def summarize_text_korean(text: str, max_tokens: int = 400) -> str:
    prompt = f"""
다음은 유튜브 영상의 자막입니다. 핵심 내용을 한국어로 400자 이내로 요약해 주세요.\n\n{text}
"""

    response = client.chat.completions.create(
        model="gpt-4o",  # 또는 gpt-3.5-turbo
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.5,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

def post_to_supabase(title, content, board_type, source, author):
    data = {
        "title": title,
        "content": content,
        "board_type": board_type,
        "source": source,
        "author": author,
    }

    try:
        response = supabase.table("posts").insert(data).execute()
        print("✅ 게시글 업로드 성공!")
        return response
    except Exception as e:
        print("❌ 업로드 실패:", e)
        return None

# Run test
if __name__ == "__main__":
    videos = search_youtube(SEARCH_QUERY)
    if videos:
        video = videos[0]  # 첫 번째 영상만 선택
        print(f"🎥 Top video: {video['title']}")
        audio_filename = "audio.mp3"
        download_3min_audio(video["url"], output_filename=audio_filename)

        result = transcribe_audio(audio_filename)
        print("🎧 Transcribed text:\n", result)

        summary = summarize_text_korean(result)

        # 🎯 영상 제목 + 요약 + 영상 링크 포함한 내용 생성
        # 🔽 유튜브 전체 검색 결과 리스트 추가
        related_videos = "\n".join(
            [f"🔸 {v['title']} 👉 {v['url']}" for v in videos]
        )
        title = f"🎥 {video['title']}"
        content = f"""🎥 영상 제목: {video['title']}

        📅 업로드 날짜: {video['published_at']}
        📺 채널: {video['channel']}
        🔗 영상 링크: {video['url']}

        📝 요약:
        {summary}

        🎧 자막 내용:
        {result}

        📺 관련 영상 목록:
        {related_videos}
   
        """
        print("📤 게시글 업로드 중...")
        print("✂️ 요약 결과:\n", content)
        post_to_supabase(
            title=title,
            content=content,
            board_type=topic["board_type"],
            source="youtube",
            author="🤖AI Bot",
        )        
    else:
        print("❗ No videos found.")

