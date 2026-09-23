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
# Liczba dni, po których starsze artykuły będą usuwane. 
# Jeśli ustawisz np. 30, to artykuły starsze niż 30 dni znikną z dysku i indexu.
# Ustaw na 0 lub None, jeśli chcesz wyłączyć całkowicie automatyczne czyszczenie.
DELETE_OLDER_THAN_DAYS = 2 
# ==========================================

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

def cleanup_old_articles():
    if not DELETE_OLDER_THAN_DAYS or DELETE_OLDER_THAN_DAYS <= 0:
        return

    print(f"Sprawdzanie i usuwanie artykułów starszych niż {DELETE_OLDER_THAN_DAYS} dni...")
    now = time.time()
    cutoff_time = now - (DELETE_OLDER_THAN_DAYS * 86400) # 86400 sekund w dniu
    
    deleted_filenames = []

    for filename in os.listdir("."):
        if filename.endswith(".html") and filename != "index.html":
            file_path = os.path.join(".", filename)
            file_mtime = os.path.getmtime(file_path)
            
            if file_mtime < cutoff_time:
                try:
                    os.remove(file_path)
                    deleted_filenames.append(filename)
                    print(f"Usunięto stary artykuł: {filename}")
                    
                    base_name = os.path.splitext(filename)[0]
                    img_path = f"{base_name}.jpg"
                    if os.path.exists(img_path):
                        os.remove(img_path)
                        print(f"Usunięto powiązany obrazek: {img_path}")
                        
                except Exception as e:
                    print(f"Błąd podczas usuwania pliku {filename}: {e}")

    if deleted_filenames:
        update_index_after_deletion(deleted_filenames)
        update_sitemap_after_deletion(deleted_filenames)

def update_index_after_deletion(deleted_filenames):
    index_file = "index.html"
    if not os.path.exists(index_file):
        return

    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()

    for filename in deleted_filenames:
        pattern = rf'<li class="article-item">.*?href="{filename}".*?</li>\s*'
        content = re.sub(pattern, '', content, flags=re.DOTALL)

    with open(index_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("Zaktualizowano plik index.html (usunięto wpisy skasowanych artykułów).")

def update_sitemap_after_deletion(deleted_filenames):
    sitemap_file = "sitemap.xml"
    if not os.path.exists(sitemap_file):
        return

    with open(sitemap_file, "r", encoding="utf-8") as f:
        content = f.read()

    for filename in deleted_filenames:
        url_to_remove = f"{BASE_URL}/{filename}"
        pattern = rf'  <url>\s*<loc>{re.escape(url_to_remove)}</loc>.*?</url>\s*'
        content = re.sub(pattern, '', content, flags=re.DOTALL)

    with open(sitemap_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("Zaktualizowano plik sitemap.xml.")

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

def get_top_trends_list():
    url = "https://trends.google.pl/trending/rss?geo=PL"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    trends = []
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:5]:
                title_elem = item.find('title')
                desc_elem = item.find('description')
                
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
                
                if not title:
                    continue
                
                news_titles = []
                for news in item.findall('{https://trends.google.com/trending/rss}news_item'):
                    news_title = news.find('{https://trends.google.com/trending/rss}news_item_title')
                    if news_title is not None and news_title.text:
                        news_titles.append(news_title.text.strip())
                
                trends.append({
                    "keyword": title,
                    "description": description,
                    "news": news_titles
                })
        return trends
    except Exception as e:
        print(f"Błąd podczas pobierania danych z Google Trends: {e}")
        return []

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
                model='gemini-2.5-flash',
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
    
    raw_text = response.text.replace("```html", "").replace("
