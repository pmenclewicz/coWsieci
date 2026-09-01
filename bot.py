import os
import re
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "pmenclewicz/szkola")
if "/" in GITHUB_REPO:
    repo_owner, repo_name = GITHUB_REPO.split("/")
    BASE_URL = f"https://{repo_owner}.github.io/{repo_name}"
else:
    BASE_URL = "https://localhost"

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
    """Odczytuje frazy z pliku manual_keywords.txt i czyści plik po odczycie."""
    file_path = "manual_keywords.txt"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            keywords = [k.strip() for k in content.split(",") if k.strip()]
            # Wyszczyść plik po odczytaniu, by nie generować tego samego przy kolejnej godzinie
            open(file_path, "w", encoding="utf-8").close()
            return keywords
    return []

def get_top_trend_data():
    url = "https://trends.google.pl/trending/rss?geo=PL"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
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
    Napisz wyczerpujący, zoptymalizowany pod SEO artykuł, który odpowiada dokładnie na intencję szukających czytelników w Google.
    
    ZASADY SEO:
    1. Tytuł (H1) musi być chwytliwy i celować w słowa długiego ogona.
    2. Przygotuj unikalny opis Meta Description (maksymalnie 160 znaków), zawierający najważniejsze słowa kluczowe i zachęcający do kliknięcia.
    3. Dobierz 2-3 angielskie tagi do wyszukiwania grafiki (np. journalist,interview).
    
    STRUKTURA WYJŚCIOWA (Użyj dokładnie tych separatorów):
    ---META_DESCRIPTION---
    [Krótki opis do 160 znaków zawierający najważniejsze frazy]
    ---TAGS---
    [angielskie tagi do zdjęcia po przecinku, np. journalist,news]
    ---ARTICLE---
    [Kod HTML artykułu: H1, wstęp, 2-3 sekcje H2 ze szczegółami, sekcja H2 z FAQ i 3 pytaniami]
    
    ZAKAZ: Nie pisz o "trendach w internecie" ani o tym, że temat jest popularny w wyszukiwarce.
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    
    raw_text = response.text.replace("```html", "").replace("```", "").strip()
    
    meta_desc = f"Aktualne informacje i szczegóły wydarzenia: {keyword}."
    image_tags = "news,technology"
    article_html = raw_text
    
    try:
        if "---META_DESCRIPTION---" in raw_text and "---ARTICLE---" in raw_text:
            parts = raw_text.split("---ARTICLE---")
            article_html = parts[1].strip()
            
            header_parts = parts[0].split("---TAGS---")
            meta_desc = header_parts[0].replace("---META_DESCRIPTION---", "").strip()
            if len(header_parts) > 1:
                image_tags = header_parts[1].strip().lower().replace(" ", "")
    except Exception as e:
        print(f"Błąd parsowania odpowiedzi Gemini, używam domyślnych struktur: {e}")
        
    return article_html, meta_desc, image_tags

def save_html_page(keyword, article_html, meta_desc, image_tags):
    slug = slugify(keyword)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    iso_date = datetime.datetime.now().isoformat()
    filename = f"{slug}.html"
    page_url = f"{BASE_URL}/{filename}"
    
    clean_tags = re.sub(r'[^a-zA-Z0-9,]', '', image_tags).strip(',') or "news"
    image_url = f"https://loremflickr.com/800/400/{clean_tags}"
    
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
        .featured-image {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 20px; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
        .ai-notice {{ font-style: italic; color: #888; margin-top: 5px; }}
    </style>
</head>
<body>
    <header><a href="index.html">Co w Sieci</a></header>
    <div class="meta">Opublikowano: {date_str}</div>
    <img src="{image_url}" alt="{page_title}" class="featured-image" onerror="this.style.display='none'">
    <main>{article_html}</main>
    <footer>
        <div>&copy; {datetime.datetime.now().year} Co w Sieci</div>
        <div class="ai-notice">Ten artykuł został automatycznie wygenerowany przez sztuczną inteligencję (AI) na podstawie aktualnych trendów.</div>
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
        <div class="ai-notice">Treści na stronie są generowane automatycznie przez sztuczną inteligencję (AI) na podstawie aktualnych trendów.</div>
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
            print(f"Generowanie artykułu dla frazy: {kw}")
            article_html, meta_desc, image_tags = generate_article_seo(kw)
            save_html_page(kw, article_html, meta_desc, image_tags)
    else:
        print("Kolejka ręczna jest pusta. Pobieranie automatycznego trendu z Google Trends...")
        keyword, context_data = get_top_trend_data()
        print(f"Pobrano temat z Google: {keyword}")
        article_html, meta_desc, image_tags = generate_article_seo(keyword, context_data)
        save_html_page(keyword, article_html, meta_desc, image_tags)
        
    print("Zakończono pracę.")
