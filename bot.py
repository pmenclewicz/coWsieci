import os
import re
import io
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from PIL import Image
from google import genai
from google.genai import types

# Konfiguracja API i środowiska
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
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
    """Odczytuje frazy z pliku manual_keywords.txt i czyści plik po odczycie."""
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
    """Pobiera najpopularniejszy trend z kanału RSS Google Trends PL."""
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
    """Generuje artykuł SEO oraz prompt po angielsku do wygenerowania grafiki AI."""
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
    3. IMAGE_PROMPT musi być szczegółowym opisem sceny po angielsku dla AI. Styl: photorealistic, 4k, news style editorial photography, neutral lighting, no text on image.
    
    STRUKTURA WYJŚCIOWA (Użyj dokładnie tych separatorów):
    ---META_DESCRIPTION---
    [Krótki opis do 160 znaków]
    ---IMAGE_PROMPT---
    [Szczegółowy opis zdjęcia po angielsku]
    ---ARTICLE---
    [Kod HTML artykułu: H1, wstęp, 2-3 sekcje H2 ze szczegółami, sekcja H2 z FAQ z 3 pytaniami]
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    raw_text = response.text.replace("```html", "").replace("
