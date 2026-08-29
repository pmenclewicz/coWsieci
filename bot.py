import os
import datetime
import feedparser
from google import genai

# Pobranie klucza z bezpiecznych ustawień
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

def get_top_trend():
    """Pobiera najbardziej zyskujące słowo z oficjalnego kanału RSS Google Trends dla Polski."""
    feed_url = "https://trends.google.pl/trending/rss?geo=PL"
    feed = feedparser.parse(feed_url)
    
    if feed.entries:
        # Pobiera tytuł pierwszego najpopularniejszego trendu
        top_keyword = feed.entries[0].title
        return top_keyword
    else:
        raise Exception("Nie udało się pobrać trendów z kanału RSS.")

def generate_article(keyword):
    """Generuje artykuł HTML za pomocą nowej biblioteki Google GenAI SDK."""
    prompt = f"""
    Jesteś dziennikarzem serwisu informacyjnego 'coWsieci'. 
    Napisz artykuł na temat zyskującego trendu w Polsce: '{keyword}'.
    
    Zwróć wyłącznie sam czysty kod HTML (bez znaczników ```html i ```), zawierający:
    - Nagłówek h1 z chwytliwym tytułem
    - Krótkie wprowadzenie (dlaczego ludzie tego dzisiaj szukają)
    - 2-3 sekcje z nagłówkami h2 objaśniające temat
    - Sekcję FAQ (3 pytania i odpowiedzi)
    
    Styl: Zwięzły, rzetelny, zoptymalizowany pod SEO.
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )
    return response.text.replace("```html", "").replace("```", "").strip()

def save_html_page(keyword, article_html):
    """Tworzy plik HTML dla danego wpisu i aktualizuje stronę główną."""
    slug = keyword.lower().replace(" ", "-").replace("/", "-")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{slug}.html"
    
    full_html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{keyword} - coWsieci</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333; }}
        header {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; margin-bottom: 20px; }}
        header a {{ text-decoration: none; color: #0066cc; font-weight: bold; font-size: 1.5rem; }}
        h1 {{ color: #111; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}
        footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 10px; font-size: 0.8rem; color: #777; }}
    </style>
</head>
<body>
    <header><a href="index.html">coWsieci</a></header>
    <div class="meta">Opublikowano: {date_str} | Trend: {keyword}</div>
    <main>{article_html}</main>
    <footer>&copy; {datetime.datetime.now().year} coWsieci - Automatyczny Serwis Informacyjny</footer>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    update_index(keyword, filename, date_str)

def update_index(keyword, filename, date_str):
    """Dodaje link do nowej strony na stronie głównej index.html."""
    entry = f'<li><span>{date_str}</span> - <a href="{filename}">{keyword}</a></li>\n'
    
    index_file = "index.html"
    if not os.path.exists(index_file):
        base_index = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>coWsieci - Najnowsze Trendy</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ padding: 10px 0; border-bottom: 1px solid #eee; }}
    </style>
</head>
<body>
    <h1>coWsieci - Aktualne Trendy</h1>
    <ul id="trends-list">
    {entry}
    </ul>
</body>
</html>"""
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(base_index)
    else:
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        updated_content = content.replace('<ul id="trends-list">', f'<ul id="trends-list">\n    {entry}')
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(updated_content)

if __name__ == "__main__":
    trend = get_top_trend()
    print(f"Pobrano trend: {trend}")
    content = generate_article(trend)
    save_html_page(trend, content)
    print("Strona wygenerowana pomyślnie.")
