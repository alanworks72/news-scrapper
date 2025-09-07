import os
os.chdir("/home/ubuntu/neu-news")
import feedparser
from openai import OpenAI
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv
from urllib.parse import urljoin

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


conn = sqlite3.connect('feeds.db')
cur = conn.cursor()

EMAIL_ADDRESS = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

with open("/home/ubuntu/neu-news/cron_log.txt", "a") as f:
    f.write(f"Script executed at {datetime.now()}\n")
    f.close()

def needs_summarization(text, min_chars=500, min_sentences=5):
    if len(text) < min_chars:
        return False
    sentence_count = sum(text.count(c) for c in ['.', '!', '?'])
    return sentence_count >= min_sentences

def summarize(text):
    response = client.chat.completions.create(
        model='gpt-4.1-nano',
        messages=[
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": f"Summarize this article concisely (7-10 sentences):\n{text}"}
        ],
        temperature=0.3,
        max_tokens=3000,
    )
    return response.choices[0].message.content.strip()

def send_md_files_via_email():
    msg = EmailMessage()
    msg["Subject"] = f"[NEU-NEWS] {today_str} 마크다운 포스트"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_RECEIVER
    msg.set_content(f"{today_str}에 생성된 블로그 글을 첨부합니다.")

    for file in os.listdir(SAVE_DIR):
        if file.endswith(".md"):
            filepath = os.path.join(SAVE_DIR, file)
            with open(filepath, "rb") as f:
                file_data = f.read()
                msg.add_attachment(file_data, maintype="text", subtype="markdown", filename=file)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("✅ 이메일 전송 완료!")
    except Exception as e:
        print("❌ 이메일 전송 실패:", e)

# def extract_image(url):
#     try:
#         resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
#         soup = BeautifulSoup(resp.text, "html.parser")
#         # 우선 og:image
#         meta = soup.find("meta", property="og:image")
#         if meta and meta.get("content"):
#             return meta["content"]
#         # fallback to first <img>
#         img = soup.find("img")
#         if img and img.get("src"):
#             return img["src"]
#     except Exception as e:
#         print("이미지 추출 오류:", e)
#     return None

def extract_image(url):
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        def is_valid_img(img):
            src = img.get("src", "")
            return src and not src.startswith("data:")

        # 상대경로 → 절대경로로 변환
        def to_absolute(src):
            return urljoin(url, src)

        all_imgs = [
            to_absolute(img.get("src")) for img in soup.find_all("img") if is_valid_img(img)
        ]

        # og:image는 보통 절대경로이지만 예외 처리
        meta = soup.find("meta", property="og:image")
        thumbnail = meta.get("content") if meta and meta.get("content") else None
        if thumbnail and thumbnail.startswith("/"):
            thumbnail = urljoin(url, thumbnail)

        return thumbnail, list(dict.fromkeys(all_imgs))  # 중복 제거
    except Exception as e:
        print("이미지 추출 오류:", e)
        return None, []


# def blog_style_post(journal, title, summary, image_url, link):
#     prompt = f"""
# 당신은 20년 경력의 전문성있는 AI, IT 기술 블로그 작가입니다.
# 아래 정보들을 참고해 Markdown 블로그 글을 작성해 주세요.

# - 제목: {title}
# - 원문 링크: {link}
# - 이미지 URL: {image_url}
# - 기사 요약 (영문):
# \"\"\"{summary}\"\"\"

# 요구 사항:
# 1. 도입부(관심 유도 2~3문장)
# 2. 본문(핵심 내용 서술, 문단 2개 이상)
# 3. 마지막에 '핵심 요약' 목록 3~4개
# 4. 언어: **자연스럽고 띄어쓰기나 줄바꿈을 적절하게 활용하는 전문적인 한국어**
# 5. 형식: **Markdown**로 작성
# 6. 표나 차트 등을 활용하여 가독성 확보
# 7. **SEO 최적화**: 키워드 사용, 제목 태그 활용 등
# 8. '핵심 요약' 부분은 **리스트 형식**으로 작성
# 9. '핵심 요약' 이후 결론 문단이나 맺음말 문장은 생성하지 마세요(이미지 예외)
#     """
#     response = openai.ChatCompletion.create(
#         model="gpt-4.1-nano",
#         messages=[
#             {"role": "system", "content": "You are a professional Korean blog writer."},
#             {"role": "user", "content": prompt}
#         ],
#         temperature=0.4,
#         max_tokens=1800,
#     )
#     return response.choices[0].message.content.strip()

def blog_style_post(journal, title, summary, thumbnail_url, body_images, link):
    prompt = f"""
    당신은 20년 경력의 전문성 있는 AI·IT 블로그 작가이며, SEO 최적화에 능한 카피라이팅 전문가입니다.
    아래 정보를 바탕으로 SEO 최적화된 제목과 구조를 가진 Markdown 블로그 글을 작성하세요.

    ---
    - 제목: {title}
    - 원문 링크: {link}
    - 썸네일 이미지 URL: {thumbnail_url}
    - 기사 요약 (영문):
    \"\"\"{summary}\"\"\"
    ---

    요구 사항:

    1. 블로그 글의 시작은 SEO 관점에서 재작성한 **매력적인 제목**을 `# 제목` 형식으로 시작하세요.  
        - 원문 제목을 그대로 사용하지 말고, 키워드(예: AI, 그래프, 관계형 데이터, 분석, 최신 등)를 포함해 검색 최적화된 블로그 제목을 생성하세요.
        - 제목 길이는 **45~60자 이내**로 작성하세요.
    2. 그 아래에는 썸네일 이미지를 `<img src="..." alt="썸네일" height="360">` 형식으로 삽입하세요.
    3. 도입부 2~3문장을 작성해 독자의 관심을 끌어주세요 (핵심 키워드 포함).
    4. 본문은 다음 예시와 같은 소제목 구조로 작성하세요 (각 문단은 5~7문장):
        예시)
        - ## 소제목이란?
        - ## 소제목의 핵심 개념과 구조
        - ## 소제목의 선행 연구 사례 비교
        - ## 소제목의 기술적 가치
        - ## 소제목의 활용 가능성과 확장성
    5. 가능하면 표, 리스트 등을 활용해 가독성과 구조를 높이세요.
    6. 마지막에는 `### 핵심 요약`이라는 소제목으로 글의 주요 내용을 4~5개 리스트로 정리하세요.
    7. '핵심 요약' 이후에는 **절대 아무 내용도 추가하지 말고 종료**하세요.
    8. Markdown 형식으로 작성하되, ```markdown 태그는 사용하지 마세요.
    9. 원문에 없는 내용은 절대로 추가하지 마세요.
    """
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a professional Korean SEO blog writer. You write clear, accurate, and keyword-optimized articles."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=1800,
    )
    return response.choices[0].message.content.strip()

# def recommend_image_insertion(md_text, image_list):
#     image_list_str = "\n".join([f"{i+1}. {url}" for i, url in enumerate(image_list)])
#     prompt = f"""
# 아래는 블로그 본문 내용입니다. (이미지는 아직 포함되지 않았습니다)
# ---
# {md_text}
# ---

# 아래는 본문과 관련된 이미지 목록입니다:
# {image_list_str}

# 요구 사항:
# 1. 우선 첨부한 이미지들이 무엇인지 면밀히 분석해주세요.
# 2. 이후 각 이미지가 들어갈 **적절한 문장을 찾아**, 그 문장 바로 아래에 `<img src="...">` 형식,
# `height="360"` 고정으로 삽입해 주세요.    예시: `<img src="..." alt="썸네일" height="360">`
# 3. 원본 {md_text}는 그대로 유지하면서 이미지 삽입만 진행해주세요.
# 4. 만약 첨부한 이미지가 **본문에 적합하지 않거나 주제에서 벗어난다면**, 해당 이미지는 사용하지 않겠습니다.
# 5. '핵심 요약' 이후 결론 문단이나 맺음말 문장은 생성하지 마세요(이미지 예외)
# 6. 이미지만 추가하시고 불필요한 다른 텍스트나 이미지 리스트 등은 **절대로** 추가하지 마세요.
# 7. 최종 결과는 **Markdown**로 반환해주세요.
# """
#     response = openai.ChatCompletion.create(
#         model="gpt-4o",
#         messages=[
#             {"role": "system", "content": "You are a Markdown editor who inserts images in the right place."},
#             {"role": "user", "content": prompt}
#         ],
#         temperature=0,
#         max_tokens=2000,
#     )
#     return response.choices[0].message.content.strip()


today_str = datetime.now().strftime("%Y-%m-%d")
SAVE_DIR = f"/home/ubuntu/neu-news/{today_str}/"
os.makedirs(SAVE_DIR, exist_ok=True)

urls = {
    'arxiv':"https://rss.arxiv.org/atom/cs.ai",
    'google research':"https://research.google/blog/rss/",
    'aws tech blog':"https://aws.amazon.com/blogs/machine-learning/feed/"
}

for journal, url in urls.items():
    feed = feedparser.parse(url)
    for entry in feed.entries[:1]:  # 한 곳에서 한 개씩
        item_id = entry.get('id', entry.link)
        title = entry.title
        link = entry.link
        published = entry.get('updated', entry.get('published', ''))
        
        print(f'Journal: {journal}\nArticle ID: {item_id}\nTitle: {title}\nLink: {link}\nPublish Date: {published}')
        
        cur.execute("SELECT id FROM feed_items WHERE item_id = ?", (item_id,))

        if cur.fetchone():
            continue

        cur.execute("""
          INSERT INTO feed_items (feed_url, item_id, title, link, published)
          VALUES (?, ?, ?, ?, ?)
        """, (url, item_id, title, link, published))
        conn.commit()

        if cur.rowcount == 0:
            continue
        
        feed_item_id = cur.lastrowid
        
        summary_input = entry.summary
        if needs_summarization(summary_input):
            summary = summarize(summary_input)
        else:
            summary = summary_input.strip()
            
        thumbnail_url, body_images = extract_image(link)
        cur.execute("UPDATE feed_items SET image_url = ? WHERE id = ?", (thumbnail_url, feed_item_id))
        conn.commit()
        
        md_blog = blog_style_post(journal, title, summary, thumbnail_url, body_images, link)
        
        if f'![썸네일 이미지]' in md_blog:
            md_blog = md_blog.replace(
            f'![썸네일 이미지]({thumbnail_url})',
            f'<img src="{thumbnail_url}" alt="썸네일" height="360">'
    )

        with open(f'{SAVE_DIR}feed_{title}.md', 'a') as f:
            f.write(md_blog)

send_md_files_via_email()

with open("/home/ubuntu/neu-news/cron_log.txt", "a") as f:
    f.write(f"Script closed at {datetime.now()}\n")
    f.close()