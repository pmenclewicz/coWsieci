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

# Konfiguracja API i środowiska
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "pmenclewicz/szkola")
BASE_URL = "https://cowsieci.pl"

def slugify(text):
    text = text.lower()
    pl_map = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'}
    for pl_char, latin_char in pl_map.items():
        text = text.replace(pl_char, latin_char)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text or "article"

def get_manual_keywords():
    file_path = "manual_keywords.txt"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            keywords = [k.strip() for k in content.split(",") if k.strip()]
            open(file_path, "w", encoding="utf-8").close()
            return keywords
    return []

def get_top_trend_data():
    url = "https://trends.google.pl/trending/rss?geo=PL"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            first_item = root.find('.//item')
            if first_item is not None:
                title = first_item.find('title').text if first_item.find('title') is not None else ""
                description = first_item.find('description').text if first_item.find('description') is not None else ""
                
                news_titles = []
                for news in first_item.findall('.//{https://trends.google.com/trending/rss}news_item'):
                    news_title = news.find('{https://trends.google.com/trending/rss}news_item_title')
                    if news_title is not None and news_title.text:
                        news_titles.append(news_title.text)
                
                context_str = f"Słowo kluczowe: {title}\nOpis sytuacji: {description}\nNagłówki wiadomości: {', '.join(news_titles)}"
                return title.strip(), context_str
    except Exception as e:
        print(f"Błąd podczas pobierania danych z Google Trends: {e}")
        
    raise Exception("Nie udało się pobrać aktualnego trendu z kanału RSS Google Trends.")

def generate_article_seo(keyword, context_data=""):
    prompt = f"""
    Jesteś ekspertem SEO i dziennikarzem serwisu informacyjnego 'Co w Sieci'.
    
    SŁOWO KLUCZOWE / TEMAT:
    {keyword}
    
    DANE KONTEKSTOWE:
    {context_data if context_data else "Brak dodatkowego kontekstu - napisz wyczerpujący artykuł na temat podanej frazy."}
    
    TWOJE ZADANIE:
    Napisz wyczerpujący, zoptymalizowany pod SEO artykuł oraz przygotuj profesjonalny prompt po angielsku do wygenerowania realistycznego zdjęcia nagłówkowego (editorial photo).
    
    ZASADY SEO I GRAFIKI:
    1. Tytuł (H1) musi być chwytliwy i celować w słowa długiego ogona.
    2. Opis Meta Description (maksymalnie 160 znaków).
    3. IMAGE_PROMPT musi być BARDZO DOSŁOWNYM i KONKRETNYM opisem wizualnym po angielsku. Skup się wyłącznie na fizycznych obiektach, ludziach, akcji i scenerii. ZABRONIONE jest używanie metafor, symboli i abstrakcyjnych koncepcji (np. zamiast "kryzys finansowy" opisz "wykresy giełdowe spadające w dół na ekranie komputera" lub "zmartwiony biznesmen"). Dodaj na końcu: "photorealistic, 4k, news style editorial photography, neutral lighting, NO text, NO letters, NO words".
    
    STRUKTURA WYJŚCIOWA (Użyj dokładnie tych separatorów):
    ---META_DESCRIPTION---
    [Krótki opis do 160 znaków]
    ---IMAGE_PROMPT---
    [Szczegółowy opis zdjęcia po angielsku]
    ---ARTICLE---
    [Kod HTML artykułu: H1, wstęp, 2-3 sekcje H2 ze szczegółami, sekcja H2 z FAQ z 3 pytaniami]
    """
    
    max_retries = 3
    response = None
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                )
            )
            break
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"Serwery Google są przeciążone (503). Próba {attempt + 1}/{max_retries}. Czekam 15 sekund...")
                time.sleep(15)
                if attempt == max_retries - 1:
                    raise e
            else:
                raise e
    
    raw_text = response.text.replace("```html", "").replace("```", "").strip()
    
    meta_desc = f"Aktualne informacje i szczegóły wydarzenia: {keyword}."
    image_prompt = f"A literal and realistic news editorial photography depicting the physical scene of: {keyword}. Photorealistic, 4k, completely textless, no letters, no words."
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

def generate_ai_image(image_prompt, output_filename):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Generowanie obrazu AI z promptem: {image_prompt}")
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=image_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                    output_mime_type="image/jpeg"
                )
            )
            for generated_image in result.generated_images:
                img = Image.open(io.BytesIO(generated_image.image.image_bytes))
                img.thumbnail((600, 337))
                img.save(output_filename, "JPEG", quality=40, optimize=True)
                
            return True
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"Przeciążenie serwera podczas generowania grafiki. Próba {attempt + 1}/{max_retries}. Czekam 15 sekund...")
                time.sleep(15)
            else:
                print(f"Nie udało się wygenerować obrazu przez AI: {e}")
                return False
    return False

def download_pexels_image(keyword, output_filename):
    if not PEXELS_API_KEY:
        print("Brak klucza PEXELS_API_KEY. Pomijam pobieranie ze stocka.")
        return False
        
    try:
        # Bierzemy max 2 słowa, aby wyszukiwanie na giełdzie zdjęć było skuteczniejsze
        search_query = " ".join(keyword.split()[:2])
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page=1&orientation=landscape"
        
        req = urllib.request.Request(url, headers={'Authorization': PEXELS_API_KEY})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            if data.get('photos') and len(data['photos']) > 0:
                image_url = data['photos'][0]['src']['large']
                
                img_req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(img_req) as img_res:
                    img_data = img_res.read()
                    
                img = Image.open(io.BytesIO(img_data))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Optymalizujemy wielkość jak przy AI, by zaoszczędzić miejsce i przyspieszyć stronę
                img.thumbnail((600, 337))
                img.save(output_filename, "JPEG", quality=70, optimize=True)
                
                print(f"Sukces! Pobrano zdjęcie z Pexels dla: {search_query}")
                return True
            else:
                print(f"Nie znaleziono odpowiedniego zdjęcia na Pexels dla hasła: {search_query}")
    except Exception as e:
        print(f"Błąd Pexels: {e}")
        
    return False

def save_html_page(keyword, article_html, meta_desc, image_prompt):
    slug = slugify(keyword)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    iso_date = datetime.datetime.now().isoformat()
    filename = f"{slug}.html"
    image_filename = f"{slug}.jpg"
    
    page_url = f"{BASE_URL}/{filename}"
    
    # Proces wyboru obrazka:
    image_caption = "Grafika wygenerowana przez sztuczną inteligencję (AI) na potrzeby artykułu."
    
    success = generate_ai_image(image_prompt, image_filename)
    if not success:
        print("Grafika AI nie powiodła się. Próba pobrania z Pexels...")
        if download_pexels_image(keyword, image_filename):
            image_caption = "Zdjęcie ilustracyjne pochodzące z darmowej bazy Pexels."
        else:
            print("Pexels też nie znalazł. Ustawianie stałego zdjęcia z LoremFlickr...")
            tags = slug.replace('-', ',')
            lock_id = sum(ord(c) for c in slug) % 10000
            image_filename = f"https://loremflickr.com/600/337/{tags}?lock={lock_id}"
            image_caption = "Zdjęcie ilustracyjne."
            
    image_url = f"{BASE_URL}/{image_filename}" if not image_filename.startswith('http') else image_filename

    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', article_html, re.IGNORECASE | re.DOTALL)
    page_title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip() if h1_match else keyword

    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title} - Co w Sieci</title>
    <meta name="description" content="{meta_desc}">
    <meta name="keywords" content="{keyword}, informacje, newsy, co w sieci, wiadomosci">
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
      "mainEntityOfPage": {{
        "@type": "WebPage",
        "@id": "{page_url}"
      }}
    }}
    </script>

    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
        header {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; margin-bottom: 20px; }}
        header a {{ text-decoration: none; color: #0066cc; font-weight: bold; font-size: 1.6rem; }}
        h1 {{ color: #111; margin-top: 15px; line-height: 1.3; }}
        h2 {{ color: #0066cc; margin-top: 25px; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 15px; }}
        .featured-image-container {{ margin-bottom: 20px; }}
        .featured-image {{ width: 100%; max-height: 450px; object-fit: cover; border-radius: 8px; display: block; }}
        .image-caption {{ font-size: 0.8rem; color: #777; margin-top: 5px; text-align: right; font-style: italic; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
        .ai-notice {{ font-style: italic; color: #888; margin-top: 5px; }}
    </style>
</head>
<body>
    <header><a href="index.html">Co w Sieci</a></header>
    <div class="meta">Opublikowano: {date_str}</div>
    <div class="featured-image-container">
        <img src="{image_filename}" alt="{page_title}" class="featured-image" onerror="this.style.display='none'">
        <div class="image-caption">{image_caption}</div>
    </div>
    <main>{article_html}</main>
    <footer>
        <div>&copy; {datetime.datetime.now().year} Co w Sieci</div>
        <div class="ai-notice">Ten artykuł został automatycznie wygenerowany.</div>
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
    <title>Co w Sieci - Najnowsze Informacje i Wiadomości</title>
    <meta name="description" content="Serwis informacyjny prezentujący najnowsze tematy i wydarzenia.">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; color: #0066cc; }}
        ul {{ list-style-type: none; padding: 0; }}
        .article-item {{ padding: 15px 0; border-bottom: 1px solid #eee; }}
        .article-item h2 {{ margin: 5px 0; font-size: 1.3rem; }}
        .article-item a {{ text-decoration: none; color: #111; }}
        .article-item a:hover {{ color: #0066cc; }}
        .date {{ color: #888; font-size: 0.85rem; }}
        .summary {{ color: #555; font-size: 0.95rem; margin-top: 5px; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
        .ai-notice {{ font-style: italic; color: #888; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>Co w Sieci</h1>
    <ul id="trends-list">
    {entry}
    </ul>
    <footer>
        <div>&copy; {datetime.datetime.now().year} Co w Sieci</div>
        <div class="ai-notice">Treści na stronie są generowane automatycznie.</div>
    </footer>
</body>
</html>"""
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(base_index)
    else:
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if f'href="{filename}"' not in content:
            updated_content = content.replace('<ul id="trends-list">', f'<ul id="trends-list">\n    {entry}')
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(updated_content)

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
        with open(sitemap_file, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
    else:
        with open(sitemap_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if f"{BASE_URL}/{filename}" not in content:
            updated_content = content.replace('</urlset>', f'{new_url_entry}\n</urlset>')
            with open(sitemap_file, "w", encoding="utf-8") as f:
                f.write(updated_content)

if __name__ == "__main__":
    manual_keywords = get_manual_keywords()
    
    if manual_keywords:
        print(f"Znaleziono {len(manual_keywords)} ręcznie dodanych fraz w kolejce. Generowanie...")
        for kw in manual_keywords:
            print(f"Generowanie artykułu i grafiki dla frazy: {kw}")
            article_html, meta_desc, image_prompt = generate_article_seo(kw)
            save_html_page(kw, article_html, meta_desc, image_prompt)
    else:
        print("Kolejka ręczna jest pusta. Pobieranie automatycznego trendu z Google Trends...")
        keyword, context_data = get_top_trend_data()
        print(f"Pobrano temat z Google: {keyword}")
        article_html, meta_desc, image_prompt = generate_article_seo(keyword, context_data)
        save_html_page(keyword, article_html, meta_desc, image_prompt)
        
    print("Zakończono pracę bota.")
