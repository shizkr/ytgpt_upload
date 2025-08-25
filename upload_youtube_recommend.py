import os
import requests
from dotenv import load_dotenv
from supabase import create_client
from topic_selector import get_random_topic
import sys
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

# Load API key from .env file
load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
MAX_RESULTS = 5

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def search_youtube(query, max_results=MAX_RESULTS):
    """
    유튜브 검색 → 상위 max_results개를 [ {title, url, channel, published_at, video_id}, ... ]로 반환
    """
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",        # 인기순
        "videoEmbeddable": "true",
        "maxResults": max_results,
        "key": API_KEY,
    }

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        print("❗ No videos found for the query.")
        return []

    results = []
    for it in items:
        vid = it["id"]["videoId"]
        sn = it["snippet"]
        results.append({
            "video_id": vid,
            "title": sn.get("title", "Untitled"),
            "channel": sn.get("channelTitle", "Unknown Channel"),
            "published_at": sn.get("publishedAt", "Unknown Date"),
            "url": f"https://youtu.be/{vid}",
        })
    print(f"🔍 Found {len(results)} videos for query '{query}'")
    return results

def get_recent_topics(days=30):
    """최근 게시된 유튜브 주제들을 가져옴"""
    try:
        # 최근 30일 이내의 게시물 제목 조회
        response = supabase.table("posts") \
            .select("title") \
            .like("title", "유튜브 추천:%") \
            .gte("created_at", f"now() - interval '{days} days'") \
            .execute()
        
        # "유튜브 추천: " 이후의 실제 주제만 추출
        topics = []
        for post in response.data:
            topic = post['title'].split("유튜브 추천: ")[-1].strip()
            topics.append(topic)
        
        return topics
    except Exception as e:
        print(f"❌ 최근 주제 조회 실패: {e}")
        return []

def post_to_supabase(title, content, board_type, source, author):
    data = {
        "title": title,
        "content": content,
        "board_type": board_type,
        "source": source,
        "format": "html",
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
    max_attempts = 5
    attempt = 0
    videos = []

    # 최근 게시된 주제들 가져오기
    recent_topics = get_recent_topics()
    print(f"🔍 최근 {len(recent_topics)}개의 주제 확인됨")

    while attempt < max_attempts:
        # 1) 랜덤 주제 새로 선택
        selected_topic = get_random_topic()
        if not selected_topic:
            print("❗ No topics found.")
            raise SystemExit(0)

        if isinstance(selected_topic, dict):
            SEARCH_QUERY = selected_topic.get("title") or selected_topic.get("query") or str(selected_topic)
            BOARD_TYPE = selected_topic.get("board_type", "youtube")
        else:
            SEARCH_QUERY = str(selected_topic)
            BOARD_TYPE = "today_youtube"

        # 중복 주제 체크
        if SEARCH_QUERY in recent_topics:
            print(f"⚠️ '{SEARCH_QUERY}'는 최근에 다룬 주제입니다. 다른 주제 선택...")
            attempt += 1
            continue

        print(f"\n🔎 '{SEARCH_QUERY}' 유튜브 검색 중... (시도 {attempt+1}/{max_attempts})")

        # 2) 유튜브 상위 10개 추출
        videos = search_youtube(SEARCH_QUERY, max_results=MAX_RESULTS)
        if videos:
            break  # 성공 시 종료

        attempt += 1
        print("❗ No videos found. 새로운 주제로 재시도합니다...")

    if not videos:
        print("❗ 최대 시도 횟수 초과. 종료합니다.")
        raise SystemExit(0)

    # 3) 추천 리스트 본문 구성 (HTML, 미리보기=첫 카드 + more, 전체=나머지)
    lines = []

    if not videos:
        content = "<p>추천할 영상이 없습니다.</p>"
    else:
        # 첫 번째 카드 (미리보기에도 노출)
        v0 = videos[0]
        v0_id = v0['url'].split("v=")[-1] if "v=" in v0['url'] else v0['url'].split("/")[-1]
        v0_thumb = f"https://img.youtube.com/vi/{v0_id}/hqdefault.jpg"

        first_card = (
            f"<style>"
            f"  @media (min-width: 768px) {{ .yt-thumb-first {{ max-width: 320px; }} }}"
            f"  @media (max-width: 767px) {{ .yt-thumb-first {{ width: 100%; height: auto; }} }}"
            f"</style>"
            f"<div style='margin-bottom:20px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;max-width:100%;'>"
            f"  <a href='{v0['url']}' target='_blank' style='text-decoration:none;color:inherit;display:block;'>"
            f"    <img src='{v0_thumb}' alt='{v0['title']}' class='yt-thumb-first' "
            f"         style='width:100%;display:block;margin:0 auto;'/>"
            f"    <div style='padding:8px;'>"
            f"      <strong>1. {v0['title']}</strong><br>"
            f"      <span>• 채널: {v0['channel']}</span><br>"
            f"      <span>• 업로드: {v0['published_at']}</span>"
            f"    </div>"
            f"  </a>"
            f"</div>"
        )

        # 나머지 카드 (전체 보기에서만 보이게 more 뒤에 배치)
        other_cards = []
        for i, v in enumerate(videos[1:], start=2):
            video_id = v['url'].split("v=")[-1] if "v=" in v['url'] else v['url'].split("/")[-1]
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

            other_cards.append(
                f"<style>"
                f"  @media (min-width: 768px) {{ .yt-thumb-{i} {{ max-width: 320px; }} }}"
                f"  @media (max-width: 767px) {{ .yt-thumb-{i} {{ width: 100%; height: auto; }} }}"
                f"</style>"
                f"<div style='margin-bottom:20px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;max-width:100%;'>"
                f"  <a href='{v['url']}' target='_blank' style='text-decoration:none;color:inherit;display:block;'>"
                f"    <img src='{thumbnail_url}' alt='{v['title']}' class='yt-thumb-{i}' "
                f"         style='width:100%;display:block;margin:0 auto;'/>"
                f"    <div style='padding:8px;'>"
                f"      <strong>{i}. {v['title']}</strong><br>"
                f"      <span>• 채널: {v['channel']}</span><br>"
                f"      <span>• 업로드: {v['published_at']}</span>"
                f"    </div>"
                f"  </a>"
                f"</div>"
            )

        today_str = datetime.now().strftime("%Y년 %m월 %d일")  # 예: 2025년 08월 14일

        # 최종 content (more 앞: 미리보기 노출, more 뒤: 전체 보기에서만 노출)
        content = (
            f"<h2>{today_str} 유튜브 추천: {SEARCH_QUERY}</h2>"
            f"{first_card}"
            f"<!-- more -->"
            + "".join(other_cards)
        )

    title = f"유튜브 추천: {SEARCH_QUERY}"

    # 4) Supabase 업로드
    print("📤 게시글 업로드 중...")
    post_to_supabase(
        title,
        content,
        board_type=BOARD_TYPE,
        source="youtube",
        author="🤖AI Bot",
    )

