import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
from io import BytesIO

st.set_page_config(page_title="Flagman Deep Parser", page_icon="🎣")

def get_soup(url, lang="uk"):
    cookies = {'i18n_redirected': lang}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9" if lang == "ru" else "uk-UA,uk;q=0.9"
    }
    try:
        session = requests.Session()
        response = session.get(url, headers=headers, cookies=cookies, timeout=20)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "lxml")
    except:
        return None

def get_subcategories(soup):
    """Ищет ссылки на подкатегории на главной странице категории"""
    sub_links = []
    # Ищем все ссылки в блоках категорий (обычно они имеют класс .item-link или лежат внутри плитки)
    cat_grid = soup.select("a.item-link")
    for link in cat_grid:
        href = link.get("href")
        if href and "/c" in href: # Проверяем, что это ссылка на категорию
            if not href.startswith("http"):
                href = "https://flagman.ua" + href
            sub_links.append(href.replace("/ru/", "/"))
    return list(dict.fromkeys(sub_links))

def get_product_links(cat_url, max_pages):
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
        time.sleep(0.3)
    return list(dict.fromkeys(links))

def parse_page_content(soup):
    if not soup: return "N/A", "N/A", {}
    product_json = {}
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            js_data = json.loads(script.string)
            if isinstance(js_data, dict) and js_data.get("@type") == "Product":
                product_json = js_data
                break
        except: continue

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else product_json.get("name", "N/A")
    desc_block = soup.select_one(".product-description-text") or soup.select_one(".product-description__content")
    description = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    
    chars = {}
    char_items = soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")
    for ci in char_items:
        p_tags = ci.find_all("p")
        if len(p_tags) >= 2:
            chars[p_tags[0].get_text(strip=True)] = p_tags[1].get_text(strip=True)
            
    return title, description, chars, product_json

# --- ИНТЕРФЕЙС ---
st.title("🎣 Flagman Deep Parser")
st.write("Можно вводить как ссылку на **подкатегорию**, так и на **главную категорию** с плитками.")

input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/ru/kotushky/c166336")
pages_limit = st.number_input("Кол-во страниц в каждом подразделе (0 = все)", min_value=0, value=1)

if st.button("Начать сканирование"):
    if not input_url:
        st.error("Введите ссылку!")
    else:
        # Приводим к UA виду для поиска
        base_url = input_url.replace("/ru/", "/")
        soup_main = get_soup(base_url)
        
        # 1. Проверяем, есть ли тут подкатегории
        sub_cats = get_subcategories(soup_main)
        
        if sub_cats:
            st.warning(f"Это главная категория. Найдено подразделов: {len(sub_cats)}")
            target_categories = sub_cats
        else:
            st.info("Это прямая подкатегория. Начинаю сбор товаров.")
            target_categories = [base_url]

        final_data = []
        skip_keys = ["Код товару", "Код товара", "Артикул", "Артикул товару"]
        
        for cat_url in target_categories:
            st.write(f"📂 Обработка раздела: {cat_url.split('/')[-2]}")
            
            product_links = get_product_links(cat_url, None if pages_limit == 0 else pages_limit)
            
            if not product_links:
                st.write("  - Товаров не найдено, пропускаю.")
                continue

            # Сбор данных о товарах
            bar = st.progress(0)
            for i, link in enumerate(product_links):
                ua_link = link.replace("/ru/", "/")
                ru_link = link.replace("flagman.ua/", "flagman.ua/ru/")
                
                soup_ua = get_soup(ua_link, "uk")
                time.sleep(0.1)
                soup_ru = get_soup(ru_link, "ru")
                
                title_ua, desc_ua, chars_ua, json_ua = parse_page_content(soup_ua)
                title_ru, desc_ru, chars_ru, json_ru = parse_page_content(soup_ru)
                
                sku = json_ua.get("sku", "N/A")
                price = json_ua.get("offers", {}).get("price", "N/A")
                brand = json_ua.get("brand", {}).get("name", "N/A")
                
                img_tags = soup_ua.select(".product-images img")
                image_urls = [img.get('src') for img in img_tags if img.get('src')]
                
                row = {
                    "Артикул": sku,
                    "Бренд": brand,
                    "Цена": price,
                    "Назва (UA)": title_ua,
                    "Название (RU)": title_ru,
                    "Опис (UA)": desc_ua,
                    "Описание (RU)": desc_ru
                }
                for idx, img_url in enumerate(image_urls[:15]): row[f"Фото {idx+1}"] = img_url
                for k, v in chars_ua.items():
                    if k not in skip_keys: row[f"{k} (UA)"] = v
                for k, v in chars_ru.items():
                    if k not in skip_keys: row[f"{k} (RU)"] = v

                row["Ссылка (UA)"] = ua_link
                row["Ссылка (RU)"] = ru_link
                final_data.append(row)
                bar.progress((i + 1) / len(product_links))
                time.sleep(0.5)

        if final_data:
            df = pd.DataFrame(final_data)
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Flagman Data', index=False)
            
            st.success(f"Завершено! Всего собрано товаров: {len(final_data)}")
            st.download_button(
                label="📥 Скачать полный Excel",
                data=output.getvalue(),
                file_name="flagman_deep_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Данные не удалось собрать.")
