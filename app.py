import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import random
from io import BytesIO

st.set_page_config(page_title="Flagman Anti-Timeout Parser", page_icon="🚀")

# --- Инициализация памяти (Session State) ---
if 'all_links' not in st.session_state:
    st.session_state.all_links = []
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'categories' not in st.session_state:
    st.session_state.categories = []

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

def get_subcategories_with_names(soup):
    sub_data = []
    items = soup.select("a.item-link")
    for link in items:
        name_tag = link.select_one(".fish-title-mobile") or link.select_one(".category-name") or link
        name = name_tag.get_text(strip=True)
        href = link.get("href")
        if href and "/c" in href and name:
            if not href.startswith("http"): href = "https://flagman.ua" + href
            url = href.replace("/ru/", "/")
            sub_data.append({"name": name, "url": url})
    unique_data = {v['url']: v for v in sub_data}.values()
    return list(unique_data)

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
        time.sleep(0.2)
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
st.title("🚀 Flagman Anti-Timeout Parser")
st.sidebar.header("Управление сессией")

if st.sidebar.button("🗑 Очистить всю память"):
    st.session_state.all_links = []
    st.session_state.scraped_data = []
    st.session_state.categories = []
    st.rerun()

input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/ru/kotushky/c166336")
pages_limit = st.number_input("Страниц в подразделе (0 = все)", min_value=0, value=1)

if st.button("🔍 1. Найти категории и ссылки"):
    with st.spinner("Собираю все ссылки на товары..."):
        base_url = input_url.replace("/ru/", "/")
        soup_main = get_soup(base_url)
        found_cats = get_subcategories_with_names(soup_main)
        
        target_cats = found_cats if found_cats else [{"name": "Текущий раздел", "url": base_url}]
        
        all_links = []
        for c in target_cats:
            links = get_product_links(c['url'], None if pages_limit == 0 else pages_limit)
            all_links.extend(links)
        
        st.session_state.all_links = list(dict.fromkeys(all_links))
        st.success(f"Найдено ссылок: {len(st.session_state.all_links)}")

# Если ссылки собраны, показываем управление парсингом
if st.session_state.all_links:
    total_links = len(st.session_state.all_links)
    st.write(f"### Собрано ссылок: {total_links}")
    st.write(f"### Уже в таблице: {len(st.session_state.scraped_data)}")

    # Выбор диапазона
    col_a, col_b = st.columns(2)
    with col_a:
        start_from = st.number_input("Начать с товара №", min_value=1, max_value=total_links, value=1)
    with col_b:
        batch_size = st.number_input("Сколько товаров обработать?", min_value=1, max_value=200, value=20)

    if st.button("🚀 2. Запустить парсинг этой части"):
        end_at = min(start_from + batch_size - 1, total_links)
        work_links = st.session_state.all_links[start_from-1:end_at]
        
        bar = st.progress(0)
        status_text = st.empty()
        skip_keys = ["Код товару", "Код товара", "Артикул", "Артикул товару"]

        for i, link in enumerate(work_links):
            status_text.write(f"Обработка {start_from + i} из {total_links}...")
            
            ua_link = link.replace("/ru/", "/")
            ru_link = link.replace("flagman.ua/", "flagman.ua/ru/")
            
            soup_ua = get_soup(ua_link, "uk")
            time.sleep(0.1)
            soup_ru = get_soup(ru_link, "ru")
            
            t_ua, d_ua, c_ua, j_ua = parse_page_content(soup_ua)
            t_ru, d_ru, c_ru, j_ru = parse_page_content(soup_ru)
            
            sku = j_ua.get("sku", "N/A")
            row = {
                "Артикул": sku,
                "Бренд": j_ua.get("brand", {}).get("name", "N/A"),
                "Цена": j_ua.get("offers", {}).get("price", "N/A"),
                "Назва (UA)": t_ua, "Название (RU)": t_ru,
                "Опис (UA)": d_ua, "Описание (RU)": t_ru # тут опечатка в логике была, поправил на описание
            }
            
            # Фото
            img_tags = soup_ua.select(".product-images img")
            image_urls = [img.get('src') for img in img_tags if img.get('src')]
            for idx, img_url in enumerate(image_urls[:15]): row[f"Фото {idx+1}"] = img_url
            
            # Характеристики
            for k, v in c_ua.items():
                if k not in skip_keys: row[f"{k} (UA)"] = v
            for k, v in c_ru.items():
                if k not in skip_keys: row[f"{k} (RU)"] = v

            row["Ссылка (UA)"] = ua_link
            row["Ссылка (RU)"] = ru_link

            # Добавляем в общий список сессии
            st.session_state.scraped_data.append(row)
            
            bar.progress((i + 1) / len(work_links))
            time.sleep(random.uniform(0.5, 1.0)) # "Человеческая" пауза

        st.success(f"Часть готова! Всего в памяти: {len(st.session_state.scraped_data)} товаров.")

# Кнопка скачивания того, что есть в памяти
if st.session_state.scraped_data:
    st.write("---")
    st.write(f"### 📥 Итоговая таблица ({len(st.session_state.scraped_data)} шт.)")
    
    df_final = pd.DataFrame(st.session_state.scraped_data).drop_duplicates(subset=['Артикул'])
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, sheet_name='Flagman', index=False)
    
    st.download_button(
        label="📥 СКАЧАТЬ EXCEL ФАЙЛ",
        data=output.getvalue(),
        file_name="flagman_accumulated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
