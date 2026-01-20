import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
from io import BytesIO

st.set_page_config(page_title="Flagman Parser Dual", page_icon="🎣")

def get_soup(url, lang="uk"):
    cookies = {'i18n_redirected': lang}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9" if lang == "ru" else "uk-UA,uk;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=20)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "lxml")
    except:
        return None

def get_product_links(cat_url, max_pages):
    # Собираем ссылки только один раз (с любой версии), так как список товаров одинаковый
    links = []
    page = 1
    while True:
        if max_pages and page > max_pages: break
        page_url = f"{cat_url}/page={page}" if page > 1 else cat_url
        soup = get_soup(page_url)
        if not soup: break
        
        scripts = soup.find_all("script", type="application/ld+json")
        page_links = []
        for script in scripts:
            try:
                data = json.loads(script.string)
                if data.get("@type") == "ItemList":
                    for element in data.get("itemListElement", []):
                        p_url = element.get("item", {}).get("url")
                        if p_url: page_links.append(p_url)
            except: continue
        
        if not page_links: break
        links.extend(page_links)
        page += 1
        time.sleep(0.5)
    return list(dict.fromkeys(links))

def parse_page_content(soup):
    """Вспомогательная функция для извлечения текстов со страницы"""
    if not soup: return "N/A", "N/A", {}
    
    # Данные из JSON для подстраховки
    product_json = {}
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            js_data = json.loads(script.string)
            if isinstance(js_data, dict) and js_data.get("@type") == "Product":
                product_json = js_data
                break
        except: continue

    # Название
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else product_json.get("name", "N/A")
    
    # Описание
    desc_block = soup.select_one(".product-description-text") or soup.select_one(".product-description__content")
    description = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    
    # Характеристики (словарь)
    chars = {}
    char_items = soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")
    for ci in char_items:
        p_tags = ci.find_all("p")
        if len(p_tags) >= 2:
            chars[p_tags[0].get_text(strip=True)] = p_tags[1].get_text(strip=True)
            
    return title, description, chars, product_json

# --- ИНТЕРФЕЙС ---
st.title("🎣 Flagman Parser (UA + RU в одной строке)")

input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/...")
pages_limit = st.number_input("Кол-во страниц (0 = все)", min_value=0, value=1)

if st.button("Начать парсинг"):
    if not input_url:
        st.error("Введите ссылку!")
    else:
        # Базовая подготовка ссылок
        clean_url = input_url.replace("/ru/", "/")
        base_links = get_product_links(clean_url, None if pages_limit == 0 else pages_limit)
        
        st.info(f"Найдено товаров: {len(base_links)}. Начинаю детальный сбор...")
        
        final_data = []
        progress_bar = st.progress(0)
        
        for i, link in enumerate(base_links):
            ua_link = link.replace("/ru/", "/")
            ru_link = link.replace("flagman.ua/", "flagman.ua/ru/")
            
            # Парсим обе версии
            soup_ua = get_soup(ua_link, "uk")
            time.sleep(0.3)
            soup_ru = get_soup(ru_link, "ru")
            
            title_ua, desc_ua, chars_ua, json_ua = parse_page_content(soup_ua)
            title_ru, desc_ru, chars_ru, json_ru = parse_page_content(soup_ru)
            
            # Общие данные (берем из UA версии)
            sku = json_ua.get("sku", "N/A")
            price = json_ua.get("offers", {}).get("price", "N/A")
            brand = json_ua.get("brand", {}).get("name", "N/A")
            
            # Фотографии (разбиваем по колонкам)
            img_tags = soup_ua.select(".product-images img")
            image_urls = [img.get('src') for img in img_tags if img.get('src')]
            
            # Собираем строку
            row = {
                "Артикул": sku,
                "Бренд": brand,
                "Цена": price,
                "Назва (UA)": title_ua,
                "Название (RU)": title_ru,
                "Опис (UA)": desc_ua,
                "Описание (RU)": desc_ru,
                "Ссылка (UA)": ua_link,
                "Ссылка (RU)": ru_link
            }
            
            # Добавляем фото в колонки "Фото 1", "Фото 2" и т.д.
            for idx, img_url in enumerate(image_urls[:15]): # Ограничим до 15 фото
                row[f"Фото {idx+1}"] = img_url
                
            # Добавляем характеристики (UA версия)
            for k, v in chars_ua.items():
                row[f"{k} (UA)"] = v
            
            # Добавляем характеристики (RU версия)
            for k, v in chars_ru.items():
                row[f"{k} (RU)"] = v

            final_data.append(row)
            progress_bar.progress((i + 1) / len(base_links))
            time.sleep(0.7)

        if final_data:
            df = pd.DataFrame(final_data)
            
            # Создаем Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Flagman Data', index=False)
            
            st.success("Парсинг успешно завершен!")
            st.download_button(
                label="📥 Скачать Excel (UA+RU)",
                data=output.getvalue(),
                file_name="flagman_combined.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
