import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import random
import re
from io import BytesIO

# Настройка страницы
st.set_page_config(page_title="Flagman Monitor Pro", page_icon="🎣", layout="wide")

# --- Инициализация Session State (БЕЗОПАСНАЯ) ---
if 'all_links' not in st.session_state:
    st.session_state.all_links = []
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'found_categories' not in st.session_state:
    st.session_state.found_categories = []
if 'current_pos' not in st.session_state:
    st.session_state.current_pos = 1

# --- Функции парсинга ---

def get_soup(url, lang="uk"):
    cookies = {'i18n_redirected': lang}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9" if lang == "ru" else "uk-UA,uk;q=0.9",
        "Referer": "https://flagman.ua/"
    }
    try:
        session = requests.Session()
        response = session.get(url, headers=headers, cookies=cookies, timeout=20)
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
    unique = {v['url']: v for v in sub_data}.values()
    return list(unique)

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
        time.sleep(0.1)
    return list(dict.fromkeys(links))

def parse_page_content(soup):
    if not soup: return "N/A", "N/A", "N/A", {}, {}
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
    
    description_clean = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    description_html = desc_block.decode_contents().strip() if desc_block else ""
    
    chars = {}
    char_items = soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")
    for ci in char_items:
        p_tags = ci.find_all("p")
        if len(p_tags) >= 2:
            chars[p_tags[0].get_text(strip=True)] = p_tags[1].get_text(strip=True)
            
    return title, description_clean, description_html, chars, product_json

# --- Интерфейс ---

st.title("🎣 Flagman Smart Monitor Pro+")

with st.sidebar:
    st.header("База данных")
    if st.button("🗑 Полный сброс"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()
    
    st.write(f"Товаров в таблице: **{len(st.session_state.scraped_data)}**")

# Шаг 1
st.subheader("1. Настройка категории")
c1, c2 = st.columns([3, 1])
with c1:
    input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/...")
with c2:
    pages_limit = st.number_input("Стр. (0=все)", min_value=0, value=1)

if st.button("🔍 Найти разделы"):
    if input_url:
        base_url = input_url.replace("/ru/", "/")
        soup_main = get_soup(base_url)
        found = get_subcategories_with_names(soup_main)
        st.session_state.found_categories = found if found else [{"name": "Текущий раздел", "url": base_url}]
        st.rerun()

# Шаг 2
if st.session_state.found_categories:
    st.subheader("2. Выбор подразделов")
    cat_map = {c['name']: c['url'] for c in st.session_state.found_categories}
    selected_cats = st.multiselect("Мониторить:", options=list(cat_map.keys()), default=list(cat_map.keys()))
    
    if st.button("🔎 Собрать ссылки"):
        all_links_list = []
        with st.spinner("Сбор всех ссылок..."):
            for name in selected_cats:
                links = get_product_links(cat_map[name], None if pages_limit == 0 else pages_limit)
                all_links_list.extend(links)
            st.session_state.all_links = list(dict.fromkeys(all_links_list))
        st.rerun()

# Шаг 3
if st.session_state.all_links:
    total_q = len(st.session_state.all_links)
    st.subheader("3. Фильтры и запуск")
    
    c_sk, c_ht = st.columns([2, 1])
    with c_sk:
        skus_raw = st.text_area("Список Артикулов для поиска (необязательно):", height=100)
    with c_ht:
        clean_html_flag = st.checkbox("Очищать HTML теги", value=True)
    
    target_skus = [x.strip() for x in re.split(r'[,\n\s]+', skus_raw) if x.strip()] if skus_raw else []

    # ИНФО ПАНЕЛЬ
    st.info(f"📋 Очередь: **{total_q}** | 📍 Позиция: **{st.session_state.current_pos}** | ✅ Найдено: **{len(st.session_state.scraped_data)}**")
    
    col_f, col_c, col_g = st.columns([1, 1, 2])
    with col_f:
        start_val = min(st.session_state.current_pos, total_q)
        start_idx = st.number_input("Начать с №", min_value=1, max_value=total_q+1, value=start_val)
    with col_c:
        batch_size = st.number_input("Кол-во для проверки", min_value=1, max_value=2000, value=100)
    
    if col_g.button("🚀 ЗАПУСТИТЬ ПАРСИНГ"):
        end_idx = min(int(start_idx) + int(batch_size) - 1, total_q)
        work_links = st.session_state.all_links[int(start_idx)-1 : end_idx]
        
        progress_bar = st.progress(0)
        st_info = st.empty()
        skip_keys = ["Код товару", "Код товара", "Артикул", "Артикул товару", "Виробник", "Производитель"]

        for i, link in enumerate(work_links):
            curr_num = int(start_idx) + i
            st_info.write(f"🔹 Проверка **{curr_num} из {total_q}**...")
            
            # Загрузка UA
            soup_ua = get_soup(link.replace("/ru/", "/"), "uk")
            if not soup_ua: continue
            
            t_ua, d_ua_cl, d_ua_rw, c_ua, j_ua = parse_page_content(soup_ua)
            sku = j_ua.get("sku", "N/A")

            # Фильтр по артикулам
            if target_skus and sku not in target_skus:
                progress_bar.progress((i + 1) / len(work_links))
                continue

            # Если прошел фильтр или фильтра нет - парсим RU
            st_info.write(f"✅ Найдено! Парсинг данных: **{sku}**")
            soup_ru = get_soup(link.replace("flagman.ua/", "flagman.ua/ru/"), "ru")
            t_ru, d_ru_cl, d_ru_rw, c_ru, j_ru = parse_page_content(soup_ru)
            
            # Чистка фото
            imgs = [img.get('src') for img in soup_ua.select(".product-images img") 
                    if img.get('src') and not img.get('src').startswith("data:image")]
            
            # Сбор строки
            row = {
                "Артикул": sku,
                "Бренд": j_ua.get("brand", {}).get("name", "N/A"),
                "Цена": j_ua.get("offers", {}).get("price", "N/A"),
                "Назва (UA)": t_ua, "Название (RU)": t_ru,
                "Опис (UA)": d_ua_cl if clean_html_flag else d_ua_rw,
                "Описание (RU)": d_ru_cl if clean_html_flag else d_ru_rw
            }
            # Фото по столбцам
            for idx, url in enumerate(imgs[:15]): row[f"Фото {idx+1}"] = url
            # Характеристики
            for k, v in c_ua.items():
                if k not in skip_keys: row[f"{k} (UA)"] = v
            for k, v in c_ru.items():
                if k not in skip_keys: row[f"{k} (RU)"] = v

            row["Ссылка (UA)"] = link.replace("/ru/", "/")
            row["Ссылка (RU)"] = link.replace("flagman.ua/", "flagman.ua/ru/")

            # Сохранение (без дублей в памяти)
            if not any(d['Артикул'] == sku for d in st.session_state.scraped_data):
                st.session_state.scraped_data.append(row)
            
            progress_bar.progress((i + 1) / len(work_links))
            time.sleep(0.05) # Минимальная пауза

        # Обновляем позицию и ПЕРЕЗАГРУЖАЕМ страницу для применения данных
        st.session_state.current_pos = min(end_idx + 1, total_q)
        st_info.empty()
        st.rerun()

# Шаг 4
if st.session_state.scraped_data:
    st.subheader("4. Результаты")
    df = pd.DataFrame(st.session_state.scraped_data)
    st.dataframe(df.head(5))
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Flagman', index=False)
    
    st.download_button(f"📥 Скачать Excel ({len(df)} товаров)", data=out.getvalue(), 
                       file_name="flagman_report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
