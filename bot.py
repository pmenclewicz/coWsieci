import os
import re
import io
import time
import json
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from PIL import Image
from google import genai
from google.genai import types

# ==========================================
# KONFIGURACJA BOTA
# ==========================================
DELETE_OLDER_THAN_DAYS = 2 
BASE_URL = "https://pmenclewicz.github.io/coWsieci"
# ==========================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def slugify(text):
    text = text.lower()
    pl_map = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'}
    for pl_char, latin_char in pl_map.items():
        text = text.replace(pl_char, latin_char)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text or "article"

def get_article_date(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})', content)
            if not match:
                match = re.search(r'Opublikowano:\s*(\d{4}-\d{2}-\d{2})', content)
            
            if match:
                date_str = match.group(1)
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                return dt.timestamp()
    except Exception as e:
        print(f"Błąd odczytu daty z pliku {file_path}: {e}")
    return os.path.getmtime(file_path)

def cleanup_old_articles():
    if not DELETE_OLDER_THAN_DAYS or DELETE_OLDER_THAN_DAYS <= 0:
        return

    print(f"Sprawdzanie i usuwanie artykułów starszych niż {DELETE_OLDER_THAN_DAYS} dni...")
    now = time.time()
    cutoff_time = now - (DELETE_OLDER_THAN_DAYS * 86400)
    deleted_filenames = []

    for filename in os.listdir("."):
        if filename.endswith(".html") and filename != "index.html":
            file_path = os.path.join(".", filename)
            file_time = get_article_date(file_path)
            
            if file_time < cutoff_time:
                try:
                    os.remove(file_path)
                    deleted_filenames.append(filename)
                    print(f"Usunięto stary artykuł: {filename}")
                    
                    base_name = os.path.splitext(filename)[0]
                    img_path = f"{base_name}.jpg"
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except Exception as e:
                    print(f"Błąd podczas usuwania pliku {filename}: {e}")

    if deleted_filenames:
        update_index_after_deletion(deleted_filenames)
        update_sitemap_after_deletion(deleted_filenames)

def update_index_after_deletion(deleted_filenames):
    index_file = "index.html"
    if not os.path.exists(index_file): return
    with open(index_file, "r", encoding="utf-8") as f: content = f.read()
    for filename in deleted_filenames:
        pattern = rf'<li class="article-item">.*?href="{filename}".*?</li>\s*'
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    with open(index_file, "w", encoding="utf-8") as f: f.write(content)

def update_sitemap_after_deletion(deleted_filenames):
    sitemap_file = "sitemap.xml"
    if not os.path.exists(sitemap_file): return
    with open(sitemap_file, "r", encoding="utf-8") as f: content = f.read()
    for filename in deleted_filenames:
        url_to_remove = f"{BASE_URL}/{filename}"
        pattern = rf'\s*<url>\s*<loc>{re.escape(url_to_remove)}</loc>.*?</url>'
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    with open(sitemap_file, "w", encoding="utf-8") as f: f.write(content)

def get_manual_keywords():
    file_path = "manual_keywords.txt"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f: content = f.read().strip()
        if content:
            keywords = [k.strip() for k in content.split(",") if k.strip()]
            open(file_path, "w", encoding="utf-8").close()
            return keywords
    return []

def get_top_news_list():
    """Pobiera NAJNOWSZE wiadomości z Google News Polska (znacznie świeższe niż Google Trends)."""
    url = "https://news.google.com/rss?hl=pl&gl=PL&ceid=PL:pl"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    news_items = []
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            for item in root.findall('.//item')[:10]:
                title = item.find('title').text.strip() if item.find('title') is not None else ""
                if title:
                    # Czyszczenie tytułu z nazwy źródła (np. "Tytuł newsa - Onet")
                    clean_title = title.split(" - ")[0]
                    news_items.append(clean_title)
        return news_items
    except Exception as e:
        print(f"Błąd pobierania Google News: {e}")
        return []

def generate_article_seo(topic):
    if not client:
        raise ValueError("Brak GEMINI_API_KEY w zmiennych środowiskowych.")

    prompt = f"""
    Jesteś profesjonalnym dziennikarzem newsowym. Twój cel to napisać ŚWIEŻY, KONKRETNY i RZETELNY artykuł prasowy na poniższy temat z ostatnich godzin:
    
    TEMAT / NAGŁÓWEK:
    {topic}
    
    INSTRUKCJA:
    1. Użyj narzędzia do przeszukiwania sieci, aby poznać WSZYSTKIE AKTUALNE FAKTY na ten temat. Sprawdź, co dokładnie się stało, kto brał w tym udział, kiedy i jakie są skutki.
    2. Pisz krótkim, dynamicznym stylem dziennikarskim (jak TVN24, Onet, RMF24).
    3. BEZWZGLĘDNY ZAKAZ:
       - Nie używaj zwrotów w stylu "W dzisiejszym świecie...", "Nie da się ukryć...", "Warto zauważyć...".
       - Nie twórz sztucznych sekcji FAQ.
       - Nie pisz ogólników. Jeśli brak konkretnych faktów, podaj najważniejsze tło sprawy.
    4. Zbuduj treść w czystym kodzie HTML (używaj <h1>, <p>, <h2>, <strong>).

    STRUKTURA WYJŚCIOWA (Użyj dokładnie tych separatorów):
    ---META_DESCRIPTION---
    [1 zwięzłe zdanie podsumowujące najważniejszy fakt – max 150 znaków]
    ---IMAGE_PROMPT---
    [A realistic editorial news photo describing the core topic in English, e.g. "editorial photo of a press conference in Warsaw, professional lighting, photorealistic, 4k, no text"]
    ---ARTICLE---
    [Kod HTML artykułu: H1 z chwytliwym tytułem, treściwy wstęp z pogrubioną kluczową informacją, 2-3 sekcje H2 szczegółowo opisujące zdarzenie]
    """
    
    print(f"Wyszukiwanie aktualnych informacji w sieci dla: {topic}...")
    
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            # Włączamy Google Search Grounding - Gemini w czasie rzeczywistym przeszukuje sieć!
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}]
                )
            )
            break
        except Exception as e:
            print(f"Błąd Gemini API (próba {attempt + 1}/{max_retries}): {e}")
            time.sleep(10)
            if attempt == max_retries - 1:
                raise e

    b_ticks = chr(96) + chr(96) + chr(96) 
    raw_text = response.text if response else ""
    raw_text = raw_text.replace(b_ticks + "html", "").replace(b_ticks, "").strip()
    
    meta_desc = f"Najnowsze informacje na temat: {topic}."
    image_prompt = f"editorial news photo about {topic}"
    article_html = raw_text
    
    try:
        if "---META_DESCRIPTION---" in raw_text and "---ARTICLE---" in raw_text:
            parts = raw_text.split("---ARTICLE---")
            article_html = parts[1].strip()
            header_parts = parts[0].split("---IMAGE_PROMPT---")
            meta_desc = header_parts[0].replace("---META_DESCRIPTION---", "").strip()
            if len(header_parts) > 1:
                image_prompt = header_parts[1].strip()
    except Exception as e:
        print(f"Błąd parsowania odpowiedzi Gemini: {e}")
        
    return article_html, meta_desc, image_prompt

# --- POBIERANIE I GENEROWANIE GRAFIK ---

def generate_ai_image(image_prompt, output_filename):
    if not client: return False
    try:
        print("Generowanie obrazu przez Google Imagen...")
        result = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1, aspect_ratio="16:9", output_mime_type="image/jpeg"
            )
        )
        for generated_image in result.generated_images:
            img = Image.open(io.BytesIO(generated_image.image.image_bytes))
            img.thumbnail((600, 337))
            img.save(output_filename, "JPEG", quality=65, optimize=True)
            return True
    except Exception as e:
        print(f"Imagen nie powiódł się: {e}")
    return False

def download_pollinations_image(image_prompt, output_filename):
    try:
        print("Pobieranie grafiki z Pollinations AI...")
        clean_prompt = urllib.parse.quote(image_prompt[:120])
        url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=600&height=337&nologo=true"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            img = Image.open(io.BytesIO(response.read()))
            if img.mode != 'RGB': img = img.convert('RGB')
            img.save(output_filename, "JPEG", quality=70, optimize=True)
            return True
    except Exception as e:
        print(f"Pollinations AI nie powiodło się: {e}")
    return False

def download_fallback_picsum(output_filename):
    try:
        print("Pobieranie zdjęcia zapasowego z Picsum...")
        url = "https://picsum.photos/600/337"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            img = Image.open(io.BytesIO(response.read()))
            if img.mode != 'RGB': img = img.convert('RGB')
            img.save(output_filename, "JPEG", quality=70, optimize=True)
            return True
    except Exception as e:
        print(f"Picsum nie powiódł się: {e}")
    return False

def process_and_save_image(keyword, image_prompt, image_filename):
    if generate_ai_image(image_prompt, image_filename):
        return "Grafika wygenerowana przez Google AI."
    if download_pollinations_image(image_prompt, image_filename):
        return "Grafika wygenerowana przez AI."
    if download_fallback_picsum(image_filename):
        return "Zdjęcie ilustracyjne."
    return ""

def save_html_page(keyword, article_html, meta_desc, image_prompt):
    slug = slugify(keyword)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    iso_date = datetime.datetime.now().isoformat()
    filename = f"{slug}.html"
    image_filename = f"{slug}.jpg"
    
    page_url = f"{BASE_URL}/{filename}"
    image_caption = process_and_save_image(keyword, image_prompt, image_filename)
    image_url = f"{BASE_URL}/{image_filename}"

    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', article_html, re.IGNORECASE | re.DOTALL)
    page_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else keyword

    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title} - Co w Sieci</title>
    <meta name="description" content="{meta_desc}">
    <link rel="canonical" href="{page_url}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{page_url}">
    <meta property="og:title" content="{page_title}">
    <meta property="og:description" content="{meta_desc}">
    <meta property="og:image" content="{image_url}">

    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "NewsArticle",
      "headline": "{page_title}",
      "image": ["{image_url}"],
      "datePublished": "{iso_date}",
      "dateModified": "{iso_date}",
      "description": "{meta_desc}",
      "mainEntityOfPage": {{ "@type": "WebPage", "@id": "{page_url}" }}
    }}
    </script>

    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #222; }}
        header {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; margin-bottom: 20px; }}
        header a {{ text-decoration: none; color: #0066cc; font-weight: bold; font-size: 1.6rem; }}
        h1 {{ color: #111; margin-top: 15px; line-height: 1.3; font-size: 1.8rem; }}
        h2 {{ color: #0066cc; margin-top: 25px; font-size: 1.3rem; }}
        .meta {{ color: #666; font-size: 0.85rem; margin-bottom: 15px; }}
        .featured-image-container {{ margin-bottom: 20px; }}
        .featured-image {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; display: block; }}
        .image-caption {{ font-size: 0.75rem; color: #777; margin-top: 5px; text-align: right; font-style: italic; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
    </style>
</head>
<body>
    <header><a href="index.html">Co w Sieci</a></header>
    <div class="meta">Opublikowano: {date_str}</div>
    <div class="featured-image-container">
        <img src="{image_filename}" alt="{page_title}" class="featured-image">
        <div class="image-caption">{image_caption}</div>
    </div>
    <main>{article_html}</main>
    <footer>
        <div>&copy; {datetime.datetime.now().year} Co w Sieci</div>
    </footer>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    update_index(page_title, filename, date_str, meta_desc)
    update_sitemap(filename, date_str)

def update_index(page_title, filename, date_str, meta_desc):
    entry = f'''<li class="article-item">
        <span class="date">{date_str}</span>
        <h2><a href="{filename}">{page_title}</a></h2>
        <p class="summary">{meta_desc}</p>
    </li>\n'''
    
    index_file = "index.html"
    if not os.path.exists(index_file):
        base_index = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Co w Sieci - Najważniejsze Wiadomości</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #222; }}
        h1 {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; color: #0066cc; }}
        ul {{ list-style-type: none; padding: 0; }}
        .article-item {{ padding: 15px 0; border-bottom: 1px solid #eee; }}
        .article-item h2 {{ margin: 5px 0; font-size: 1.2rem; }}
        .article-item a {{ text-decoration: none; color: #111; }}
        .article-item a:hover {{ color: #0066cc; }}
        .date {{ color: #888; font-size: 0.8rem; }}
        .summary {{ color: #555; font-size: 0.9rem; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>Co w Sieci</h1>
    <ul id="trends-list">
    {entry}
    </ul>
</body>
</html>"""
        with open(index_file, "w", encoding="utf-8") as f: f.write(base_index)
    else:
        with open(index_file, "r", encoding="utf-8") as f: content = f.read()
        if f'href="{filename}"' not in content:
            updated_content = content.replace('<ul id="trends-list">', f'<ul id="trends-list">\n    {entry}')
            with open(index_file, "w", encoding="utf-8") as f: f.write(updated_content)

def update_sitemap(filename, date_str):
    sitemap_file = "sitemap.xml"
    new_url_entry = f"""  <url>
    <loc>{BASE_URL}/{filename}</loc>
    <lastmod>{date_str}</lastmod>
    <changefreq>never</changefreq>
    <priority>0.8</priority>
  </url>"""

    if not os.path.exists(sitemap_file):
        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{BASE_URL}/index.html</loc>
    <lastmod>{date_str}</lastmod>
    <changefreq>always</changefreq>
    <priority>1.0</priority>
  </url>
{new_url_entry}
</urlset>"""
        with open(sitemap_file, "w", encoding="utf-8") as f: f.write(sitemap_content)
    else:
        with open(sitemap_file, "r", encoding="utf-8") as f: content = f.read()
        if f"{BASE_URL}/{filename}" not in content:
            updated_content = content.replace('</urlset>', f'{new_url_entry}\n</urlset>')
            with open(sitemap_file, "w", encoding="utf-8") as f: f.write(updated_content)

def select_best_news(news_items):
    """Szybko wybiera najbardziej konkretny news ze świeżej listy."""
    if not news_items: return None
    # Wybieramy pierwszy gorący news z Google News
    return news_items[0]

if __name__ == "__main__":
    cleanup_old_articles()

    manual_keywords = get_manual_keywords()
    
    if manual_keywords:
        print(f"Znaleziono {len(manual_keywords)} ręcznie dodanych tematów.")
        for kw in manual_keywords:
            print(f"Generowanie artykułu: {kw}")
            article_html, meta_desc, image_prompt = generate_article_seo(kw)
            save_html_page(kw, article_html, meta_desc, image_prompt)
    else:
        print("Pobieranie najświeższych newsów z Google News Polska...")
        news_list = get_top_news_list()
        
        if news_list:
            selected_news = select_best_news(news_list)
            print(f"Wybrany aktualny news: {selected_news}")
            
            article_html, meta_desc, image_prompt = generate_article_seo(selected_news)
            save_html_page(selected_news, article_html, meta_desc, image_prompt)
        else:
            print("Nie udało się pobrać aktualności.")
            
    print("Praca bota zakończona.")
