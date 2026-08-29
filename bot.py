import os
import re
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from google import genai

# Pobranie klucza API z ustawień repozytorium GitHub
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

# Automatyczne ustalenie adresu strony na GitHub Pages
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "user/repo")
if "/" in GITHUB_REPO:
    repo_owner, repo_name = GITHUB_REPO.split("/")
    BASE_URL = f"https://{repo_owner}.github.io/{repo_name}"
else:
    BASE_URL = "https://localhost"

def slugify(text):
    """Tworzy bezpieczną dla adresów URL i plików nazwę z dowolnego ciągu znaków."""
    text = text.lower()
    # Podmiana polskich znaków
    pl_map = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'}
    for pl_char, latin_char in pl_map.items():
        text = text.replace(pl_char, latin_char)
    # Zostawiamy tylko litery, cyfry i spacje, a potem zamieniamy spacje na myślniki
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text or "article"

def get_top_trend_data():
    """Pobiera nie tylko nagłówek, ale i opis oraz artykuły powiązane z trendem z Google Trends."""
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
                
                # Pobieramy wiadomości prasowe powiązane z tym trendem (jeśli są w RSS)
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

def generate_article_and_image_tags(keyword, context_data):
    """Generuje treść artykułu oraz precyzyjne angielskie tagi do dobierania zdjęć."""
    prompt = f"""
    Jesteś profesjonalnym dziennikarzem i ekspertem SEO serwisu informacyjnego 'Co w Sieci'.
    
    DANE WEJŚCIOWE Z GOOGLE TRENDS:
    {context_data}
    
    TWOJE ZADANIE:
    1. Napisz artykuł zoptymalizowany pod kątem tego, czego dokładnie ludzie szukają w Google w tym momencie.
    2. Na samym końcu odpowiedzi wygeneruj linię tekstową z 2-3 angielskimi słowami kluczowymi (po przecinku), które idealnie opisują ten temat na potrzeby wyszukiwarki zdjęć (np. dla meczu piłkarskiego: soccer,stadium; dla polityki: politics,government).
    
    STRUKTURA WYJŚCIOWA:
    Zwróć treść w formacie:
    ---ARTICLE---
    [czysty kod HTML artykułu: h1, intro, h2, faq]
    ---TAGS---
    [angielskie słowa kluczowe oddzielone przecinkami, bez spacji, np. stadium,soccer]

    ZASADY ARTYKUŁU HTML:
    - Nagłówek h1 (chwytliwy, zoptymalizowany pod wyszukiwania)
    - Wprowadzenie z podsumowaniem najważniejszego faktu na samym początku
    - 2-3 sekcje z nagłówkami h2 opisujące szczegóły
    - Sekcja FAQ z nagłówkiem h2 i 3 konkretnymi pytaniami i odpowiedziami
    - ZAKAZ: Nie pisz o "popularności w Google" ani o "trendach".
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    
    raw_text = response.text.replace("```html", "").replace("```", "").strip()
    
    article_html = raw_text
    image_tags = "news,technology"
    
    if "---ARTICLE---" in raw_text and "---TAGS---" in raw_text:
        parts = raw_text.split("---TAGS---")
        article_html = parts[0].replace("---ARTICLE---", "").strip()
        image_tags = parts[1].strip().lower().replace(" ", "")
    
    return article_html, image_tags

def save_html_page(keyword, article_html, image_tags):
    """Tworzy plik HTML ze zdjęciem zmieniającym się przy każdym odświeżeniu, ale zoptymalizowanym pod kątem kategorii."""
    slug = slugify(keyword)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{slug}.html"
    
    # Czyszczenie tagów ze znaków niedozwolonych
    clean_tags = re.sub(r'[^a-zA-Z0-9,]', '', image_tags).strip(',')
    if not clean_tags:
        clean_tags = "news"
        
    # Tworzenie dynamicznego linku z wieloma dopasowanymi tagami po angielsku
    image_url = f"https://loremflickr.com/800/400/{clean_tags}"
    
    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{keyword} - Co w Sieci</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
        header {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; margin-bottom: 20px; }}
        header a {{ text-decoration: none; color: #0066cc; font-weight: bold; font-size: 1.6rem; }}
        h1 {{ color: #111; margin-top: 15px; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 15px; }}
        .featured-image {{ width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 20px; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
    </style>
</head>
<body>
    <header><a href="index.html">Co w Sieci</a></header>
    <div class="meta">Opublikowano: {date_str}</div>
    <img src="{image_url}" alt="{keyword}" class="featured-image" onerror="this.style.display='none'">
    <main>{article_html}</main>
    <footer>&copy; {datetime.datetime.now().year} Co w Sieci</footer>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    update_index(keyword, filename, date_str)
    update_sitemap(filename, date_str)

def update_index(keyword, filename, date_str):
    """Dodaje link do nowej strony na stronie głównej index.html bez powielania wpisów."""
    entry = f'<li><span>{date_str}</span> - <a href="{filename}">{keyword}</a></li>\n'
    
    index_file = "index.html"
    if not os.path.exists(index_file):
        base_index = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Co w Sieci</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; color: #0066cc; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ padding: 12px 0; border-bottom: 1px solid #eee; font-size: 1.1rem; }}
        li a {{ text-decoration: none; color: #111; font-weight: 500; }}
        li a:hover {{ color: #0066cc; }}
        li span {{ color: #888; font-size: 0.9rem; margin-right: 10px; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 15px; font-size: 0.85rem; color: #777; text-align: center; }}
    </style>
</head>
<body>
    <h1>Co w Sieci</h1>
    <ul id="trends-list">
    {entry}
    </ul>
    <footer>&copy; {datetime.datetime.now().year} Co w Sieci</footer>
</body>
</html>"""
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(base_index)
    else:
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Zabezpieczenie przed duplikowaniem wpisu na stronie głównej
        if f'href="{filename}"' not in content:
            updated_content = content.replace('<ul id="trends-list">', f'<ul id="trends-list">\n    {entry}')
            with open(index_file, "w", encoding="utf-8") as f:
                f.write(updated_content)

def update_sitemap(filename, date_str):
    """Tworzy lub aktualizuje plik sitemap.xml dla robotów Google bez powielania wpisów."""
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
        
        # Zabezpieczenie przed duplikowaniem wpisu w sitemap.xml
        if f"{BASE_URL}/{filename}" not in content:
            updated_content = content.replace('</urlset>', f'{new_url_entry}\n</urlset>')
            with open(sitemap_file, "w", encoding="utf-8") as f:
                f.write(updated_content)

if __name__ == "__main__":
    keyword, context_data = get_top_trend_data()
    print(f"Pobrano temat: {keyword}")
    article_html, image_tags = generate_article_and_image_tags(keyword, context_data)
    print(f"Dopasowane tagi do obrazka: {image_tags}")
    save_html_page(keyword, article_html, image_tags)
    print("Strona, index.html oraz sitemap.xml zostały zaktualizowane pomyślnie.")
