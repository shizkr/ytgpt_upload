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
def get_upcoming_weekend_range(now: datetime):
    """금요일 실행 기준: 이번 주 토요일 00:00 ~ 일요일 23:59:59 (로컬)"""
    weekday = now.weekday()  # Mon=0 ... Sun=6
    days_until_sat = (5 - weekday) % 7
    sat = (now + timedelta(days=days_until_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
    sun_end = (sat + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
    return sat, sun_end

# ---------- CHATGPT ----------
SYSTEM_PROMPT = """You are a local weekend concierge for Southern California.
Return concise, family-friendly weekend recommendations for Orange County and Los Angeles.
If specific timed public events are uncertain, include evergreen/weekend-suitable activities (markets, hikes, beaches, museums, seasonal shows).
ALWAYS return strict JSON following the provided schema. Do not include markdown fences or extra text.
Times should be local PT. Avoid hallucinating precise addresses; if unsure set address to "" and keep venue generic.
Limit to MAX_ITEMS per region.
"""

USER_PROMPT_TEMPLATE = """
TASK: Create weekend recommendations for {date_label} (Sat~Sun).
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
- Mix of specific events (if reasonably likely) + evergreen ideas (hikes, beaches, farmers markets, museums, piers, theme parks, scenic drives).
- Diversity: family-friendly, outdoor, budget/free options included.
- OC 예시 아이디어: Laguna Beach Heisler Park trail, Crystal Cove hike & tide pools, Irvine Spectrum weekend live music, OC Fair & Event Center events, Dana Point harbor stroll, Huntington Dog Beach.
- LA 예시 아이디어: Griffith Observatory lawn, The Getty/The Broad, Santa Monica/Venice bike path, Grand Central Market, LACMA Urban Light.
- Keep each description short (we will render separately).
- Return JSON only.
"""

def ask_chatgpt_for_events(regions, sat, sun_end, max_items=MAX_EVENTS_PER_REGION):
    date_label = f"{sat.strftime('%Y-%m-%d')} ~ {sun_end.strftime('%Y-%m-%d')}"
    user_prompt = USER_PROMPT_TEMPLATE.format(
        date_label=date_label,
        regions=", ".join(regions),
        max_items=max_items
    )

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # 가성비 모델 권장
            temperature=0.4,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.replace("MAX_ITEMS", str(max_items))},
                {"role": "user", "content": user_prompt}
            ]
        )
        text = resp.choices[0].message.content
        data = json.loads(text)
        return data
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
        f"<h2>{today_str} OC·LA 주말 액티비티 추천 ({weekend_label})</h2>"
        f"<p>이번 주말 가족·커플·친구와 즐길 거리 모음입니다. 즐거운 주말 보내세요! ☀️</p>"
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

# ---------- MAIN ----------
if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("❗ OPENAI_API_KEY 가 없습니다. .env를 확인하세요.")
        raise SystemExit(1)

    now = datetime.now()
    sat, sun_end = get_upcoming_weekend_range(now)
    weekend_label = f"{sat.strftime('%Y-%m-%d')} ~ {(sat + timedelta(days=1)).strftime('%Y-%m-%d')}"
    print(f"📅 대상 주말: {weekend_label}")

    gpt_data = ask_chatgpt_for_events(REGIONS, sat, sun_end, MAX_EVENTS_PER_REGION)

    if not gpt_data or not gpt_data.get("regions"):
        print("❗ 유효한 이벤트 데이터를 받지 못했습니다. 종료합니다.")
        raise SystemExit(1)

    title = f"OC·LA 주말 이벤트 추천: {weekend_label}"
    content = build_content(gpt_data, weekend_label)

    print("📤 게시글 업로드 중...")
    post_to_supabase(
        title=title,
        content=content,
        board_type=BOARD_TYPE,
        source=SOURCE,
        author=AUTHOR,
    )
