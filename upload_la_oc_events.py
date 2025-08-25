import os
import json
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
import openai

sys.stdout.reconfigure(encoding='utf-8')

# ---------- ENV ----------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY

# ---------- CONFIG ----------
BOARD_TYPE = "ocla_weekend"     # 원하는 게시판 타입
AUTHOR = "🤖AI Bot"
SOURCE = "chatgpt"
REGIONS = ["Orange County, CA", "Los Angeles, CA"]
MAX_EVENTS_PER_REGION = 6

# ---------- DATE ----------
def get_upcoming_week_range(now: datetime):
    """현재 시점부터 7일간의 범위 반환
    Returns: 오늘 00:00 ~ 7일 후 23:59:59 (로컬)"""
    
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0)
    
    print(f"🗓 현재: {now.strftime('%Y-%m-%d %H:%M')} ({['월','화','수','목','금','토','일'][now.weekday()]}요일)")
    print(f"🗓 추천 기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    
    return start, end

# ---------- CHATGPT ----------
SYSTEM_PROMPT = """You are a local activities recommender for Southern California.
Return concise, family-friendly week recommendations for Orange County and Los Angeles.
If specific timed public events are uncertain, include evergreen/week/weekend-suitable activities (markets, hikes, beaches, museums, seasonal shows).
ALWAYS return strict JSON following the provided schema. Do not include markdown fences or extra text.
Times should be local PT. Avoid hallucinating precise addresses; if unsure set address to "" and keep venue generic.
Limit to MAX_ITEMS per region.
"""

USER_PROMPT_TEMPLATE = """
TASK: Create week and weekend recommendations for {date_label}.
QUESTION: {question}
REGIONS: {regions}
MAX_ITEMS: {max_items}

Schema:
{{
  "regions": [
    {{
      "name": "Orange County, CA",
      "events": [
        {{
          "title": "string",
          "start": "YYYY-MM-DD HH:MM",
          "end": "YYYY-MM-DD HH:MM",
          "venue": "string",
          "address": "string",
          "category": "event|outdoor|museum|market|food|family|music|sports|seasonal",
          "url": "https://...",
          "image": "https://... (optional)"
        }}
      ]
    }}
  ],
  "disclaimer": "string"
}}

Guidelines:
- Mix of specific events (if reasonably likely) + evergreen ideas (hikes, beaches, farmers markets, museums, piers, theme parks, scenic drives, others).
- Diversity: family-friendly, outdoor, budget/free options included, other activities.
- OC 예시 아이디어: Laguna Beach Heisler Park trail
- LA 예시 아이디어: Griffith Observatory lawn
- Keep each description short (we will render separately).
- Return JSON only.
"""
CATEGORIES = [
    ["outdoor", "food", "family"],
    ["museum", "market", "sports"],
    ["music", "seasonal", "event"]
]

def get_rotating_categories():
    # 현재 주차에 따라 다른 카테고리 조합 반환
    week_number = datetime.now().isocalendar()[1]
    return CATEGORIES[week_number % len(CATEGORIES)]

def get_previous_recommendations():
    # 최근 몇 주간의 추천 내역을 가져와서 중복 방지
    response = supabase.table("posts").select("content").eq("board_type", BOARD_TYPE).order("created_at", desc=True).limit(4).execute()
    return response.data

def ask_chatgpt_for_events(regions, sat, sun_end, max_items=MAX_EVENTS_PER_REGION, question=None):
    date_label = f"{sat.strftime('%Y-%m-%d')} ~ {sun_end.strftime('%Y-%m-%d')}"
    rotating_categories = get_rotating_categories()
    previous_recommendations = get_previous_recommendations()
    user_prompt = USER_PROMPT_TEMPLATE.format(
        date_label=date_label,
        question=question,
        regions=", ".join(regions),
        max_items=max_items,
        preferred_categories=", ".join(rotating_categories),
        avoid_previous=previous_recommendations
    )

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print("💬 Asking ChatGPT for event recommendations...")
    print(user_prompt)  # 디버깅용 전체 프롬프트 출력

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",  # 가성비 모델 권장
            temperature=0.8,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.replace("MAX_ITEMS", str(max_items))},
                {"role": "user", "content": user_prompt}
            ]
        )
        text = resp.choices[0].message.content
        print("📝 ChatGPT 응답:", text[:300] + "...") # 응답 내용 일부 출력

        try:
            data = json.loads(text)
            if not data.get("regions"):
                print("❌ regions 데이터가 없습니다")
                return {}
            return data
        except json.JSONDecodeError as e:
            print("❌ JSON 파싱 실패:", e)
            print("받은 텍스트:", text)
            return {}
        
    except Exception as e:
        print("❌ ChatGPT 요청/파싱 실패:", e)
        return {}

# ---------- RENDER ----------
def render_event_card(idx: int, ev: dict):
    img_html = ""
    if ev.get("image"):
        img_html = f"<img src='{ev['image']}' alt='{ev['title']}' style='width:100%;display:block;margin:0 auto;'/>"

    def fmt(s):
        return s or ""

    return (
        "<div style='margin-bottom:20px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;max-width:100%;'>"
        f"  <a href='{fmt(ev.get('url'))}' target='_blank' style='text-decoration:none;color:inherit;display:block;'>"
        f"    {img_html}"
        f"    <div style='padding:10px;'>"
        f"      <strong>{idx}. {fmt(ev.get('title'))}</strong><br>"
        f"      <span>• 일정: {fmt(ev.get('start'))} ~ {fmt(ev.get('end'))}</span><br>"
        f"      <span>• 유형: {fmt(ev.get('category'))}</span><br>"
        f"      <span>• 장소: {fmt(ev.get('venue'))}</span><br>"
        f"      <span>• 주소: {fmt(ev.get('address')) or '-'}</span>"
        f"    </div>"
        f"  </a>"
        "</div>"
    )

def build_content(gpt_json, weekend_label):
    sections = []
    for region in gpt_json.get("regions", []):
        name = region.get("name", "Region")
        events = region.get("events", [])
        if not events:
            sections.append(f"<h3>📍 {name}</h3><p>추천 항목이 없습니다.</p>")
            continue
        cards = [render_event_card(i+1, ev) for i, ev in enumerate(events)]
        sections.append(f"<h3>📍 {name}</h3>" + "".join(cards))

    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    disclaimer = gpt_json.get("disclaimer", "정확한 일정은 공식 홈페이지에서 확인하세요.")
    content = (
        f"<h2>{today_str} OC·LA 주간 액티비티 추천 ({weekend_label})</h2>"
        f"<p>이번 주 가족·커플·친구와 즐길 거리 모음입니다. 즐거운 시간을 보내세요! ☀️</p>"
        f"<!-- more -->"
        + "".join(sections) +
        f"<p style='color:#6b7280;font-size:12px;margin-top:12px;'>※ {disclaimer}</p>"
    )
    return content

# ---------- SUPABASE ----------
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

import random

# 다양한 질문 템플릿 추가
WEEKEND_QUESTIONS = [
    {"question": "이번 주말 OC와 LA에서 할만한 재미있는 활동이나 이벤트를 알려줘. 실내/실외 활동 모두 포함해서 추천해줘.", 
     "title_format": "이번 주말 뭐하지? OC·LA 추천 액티비티: {date}"},
    {"question": "초등학생 자녀가 있는 가족이 주말에 즐길 수 있는 교육적이면서도 재미있는 장소나 활동을 추천해줘. 박물관, 동물원, 체험활동 등 다양하게 알려줘.", 
     "title_format": "가족과 함께! OC·LA 주말 나들이 명소: {date}"},
    {"question": "20-30대 커플이 주말에 가면 좋을 로맨틱하고 분위기 있는 데이트 장소를 추천해줘. 식사와 카페, 산책하기 좋은 곳이나 특별한 체험도 포함해서 알려줘.", 
     "title_format": "커플 데이트 스팟! OC·LA 주말 추천: {date}"},
    {"question": "20대 친구들끼리 주말에 놀러가기 좋은 핫플레이스를 추천해줘. 사진 찍기 좋고 트렌디한 장소나 액티비티 위주로 알려줘.", 
     "title_format": "친구들과 함께! OC·LA 주말 핫플레이스: {date}"},
    {"question": "이번 주말 OC와 LA에서 열리는 특별한 행사나 이벤트, 페스티벌이 있다면 알려줘. 시간과 장소도 구체적으로 포함해줘.", 
     "title_format": "특별한 주말! OC·LA 이벤트 모음: {date}"},
    {"question": "날씨 좋은 주말에 즐기기 좋은 하이킹 코스, 비치, 공원 등 야외 명소를 추천해줘. 각 장소의 특징과 추천 포인트도 설명해줘.", 
     "title_format": "야외 활동하기 좋은 OC·LA 주말 명소: {date}"},
    {"question": "주말 브런치로 유명한 맛집과 식사 후에 즐기기 좋은 근처 산책로나 카페를 추천해줘. 분위기 좋은 장소 위주로 알려줘.", 
     "title_format": "주말 브런치 & 액티비티 추천! OC·LA 가이드: {date}"},
    {"question": "주말에 즐기기 좋은 미술관, 박물관, 공연장 등 문화예술 명소를 추천해줘. 현재 진행 중인 특별 전시나 공연 정보도 포함해서 알려줘.", 
     "title_format": "문화의 주말! OC·LA 예술/전시 추천: {date}"}
]

def get_random_question():
    return random.choice(WEEKEND_QUESTIONS)

# ---------- MAIN ----------
if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("❗ OPENAI_API_KEY 가 없습니다. .env를 확인하세요.")
        raise SystemExit(1)

    now = datetime.now()
    start, end = get_upcoming_week_range(now)
    week_label = f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
    print(f"📅 대상 기간: {week_label}")

    # 랜덤 질문 선택
    selected_question = get_random_question()

    print(f"❓ 선택된 질문: {selected_question['question']}")

    # ChatGPT 요청 시 질문 포함
    gpt_data = ask_chatgpt_for_events(
        regions=REGIONS,
        sat=start,
        sun_end=end,
        max_items=MAX_EVENTS_PER_REGION,
        question=selected_question["question"]
    )

    if not gpt_data or not gpt_data.get("regions"):
        print("❗ 유효한 이벤트 데이터를 받지 못했습니다. 종료합니다.")
        raise SystemExit(1)

    # 선택된 질문에 맞는 제목 포맷 사용
    title = selected_question["title_format"]
    content = build_content(gpt_data, week_label)

    print("📤 게시글 업로드 중...")
    post_to_supabase(
        title=title,
        content=content,
        board_type=BOARD_TYPE,
        source=SOURCE,
        author=AUTHOR,
    )
