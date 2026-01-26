import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import random
import re
from io import BytesIO

st.set_page_config(page_title="Flagman Parser Elite", page_icon="🎣", layout="wide")

# --- Инициализация Session State ---
if 'all_links' not in st.session_state:
    st.session_state.all_links = []
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'found_categories' not in st.session_state:
    st.session_state.found_categories = []
if 'next_start_node' not in st.session_state:
    st.session_state.next_start_node = 1

# --- Вспомогательные функции ---

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

def get_subcategories(soup):
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
        found_on_page = False
        for script in scripts:
            try:
                data = json.loads(script.string)
                if data.get("@type") == "ItemList":
                    for element in data.get("itemListElement", []):
                        p_url = element.get("item", {}).get("url")
                        if p_url: 
                            links.append(p_url)
                            found_on_page = True
            except: continue
        if not found_on_page: break
        links.extend(page_links if 'page_links' in locals() else [])
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
    
    d_clean = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    d_html = desc_block.decode_contents().strip() if desc_block else ""
    
    chars = {}
    char_items = soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")
    for ci in char_items:
        p_tags = ci.find_all("p")
        if len(p_tags) >= 2:
            chars[p_tags[0].get_text(strip=True)] = p_tags[1].get_text(strip=True)
            
    return title, d_clean, d_html, chars, product_json

# --- Интерфейс ---

st.title("🎣 Flagman Monitor Smart Pro")

with st.sidebar:
    st.header("Управление базой")
    if st.button("🗑 Очистить всё"):
        st.session_state.all_links = []
        st.session_state.scraped_data = []
        st.session_state.found_categories = []
        st.session_state.next_start_node = 1
        st.rerun()
    st.write(f"Товаров в памяти: **{len(st.session_state.scraped_data)}**")

# --- Шаг 1 ---
st.subheader("1. Ссылка на раздел")
col_u, col_p = st.columns([3, 1])
with col_u:
    input_url = st.text_input("Введите URL (UA или RU)", placeholder="https://flagman.ua/...")
with col_p:
    pages_limit = st.number_input("Стр. (0=все)", min_value=0, value=1)

if st.button("🔍 Проверить разделы"):
    if input_url:
        base_url = input_url.replace("/ru/", "/")
        soup = get_soup(base_url)
        found = get_subcategories(soup)
        st.session_state.found_categories = found if found else [{"name": "Текущий раздел", "url": base_url}]
        st.rerun()

# --- Шаг 2 ---
if st.session_state.found_categories:
    st.subheader("2. Выбор категорий")
    cat_dict = {c['name']: c['url'] for c in st.session_state.found_categories}
    selected = st.multiselect("Что мониторим:", options=list(cat_dict.keys()), default=list(cat_dict.keys()))
    
    if st.button("🔎 Сформировать очередь ссылок"):
        links_acc = []
        with st.spinner("Собираю ссылки..."):
            for n in selected:
                links_acc.extend(get_product_links(cat_dict[n], None if pages_limit == 0 else pages_limit))
            st.session_state.all_links = list(dict.fromkeys(links_acc))
        st.success(f"Очередь создана: {len(st.session_state.all_links)} ссылок")
        st.rerun()

# --- Шаг 3 ---
if st.session_state.all_links:
    total_links = len(st.session_state.all_links)
    st.subheader("3. Фильтры и Парсинг")
    
    # Контейнер для настроек
    with st.expander("Настройки фильтра и очистки", expanded=True):
        skus_raw = st.text_area("Список Артикулов (если нужно выбрать конкретные):")
        clean_html = st.checkbox("Очищать HTML теги в описании", value=True)
    
    target_skus = [x.strip() for x in re.split(r'[,\n\s]+', skus_raw) if x.strip()] if skus_raw else []

    # Инфо-плашка
    st.info(f"📋 Очередь: **{total_links}** | 📍 Позиция: **{st.session_state.next_start_node}** | ✅ Найдено и сохранено: **{len(st.session_state.scraped_data)}**")

    # Форма для защиты от "Bad message format"
    with st.form("parsing_form"):
        c_f, c_c = st.columns(2)
        with c_f:
            start_num = st.number_input("Начать с №", min_value=1, max_value=total_links, value=st.session_state.next_start_node)
        with c_c:
            count_to_parse = st.number_input("Кол-во для проверки", min_value=1, max_value=2000, value=100)
        
        submit_btn = st.form_submit_button("🚀 ЗАПУСТИТЬ ПАРСИНГ ПАЧКИ")

    if submit_btn:
        end_at = min(int(start_num) + int(count_to_parse) - 1, total_links)
        work_list = st.session_state.all_links[int(start_num)-1 : end_at]
        
        p_bar = st.progress(0)
        p_status = st.empty()
        
        # Ключи характеристик, которые удаляем (дубли)
        skip_list = ["Код товару", "Код товара", "Артикул", "Артикул товару", "Виробник", "Производитель"]

        for i, link in enumerate(work_list):
            curr_pos = int(start_num) + i
            p_status.write(f"⏳ Проверка {curr_pos} из {total_links}...")
            
            # UA
            soup_ua = get_soup(link.replace("/ru/", "/"), "uk")
            if not soup_ua: continue
            
            t_ua, d_ua_c, d_ua_h, c_ua, j_ua = parse_page_content(soup_ua)
            sku = j_ua.get("sku", "N/A")

            # Фильтр SKU
            if target_skus and sku not in target_skus:
                p_bar.progress((i + 1) / len(work_list))
                continue

            # Если ок - RU
            p_status.write(f"✅ Парсинг данных: **{sku}**")
            soup_ru = get_soup(link.replace("flagman.ua/", "flagman.ua/ru/"), "ru")
            t_ru, d_ru_c, d_ru_h, c_ru, j_ru = parse_page_content(soup_ru)
            
            # Фото без мусора
            img_list = [img.get('src') for img in soup_ua.select(".product-images img") 
                       if img.get('src') and not img.get('src').startswith("data:")]
            if not img_list:
                og = soup_ua.find("meta", property="og:image")
                if og: img_list.append(og["content"])

            row = {
                "Артикул": sku,
                "Бренд": j_ua.get("brand", {}).get("name", "N/A"),
                "Цена": j_ua.get("offers", {}).get("price", "N/A"),
                "Назва (UA)": t_ua, 
                "Название (RU)": t_ru,
                "Опис (UA)": d_ua_c if clean_html else d_ua_h,
                "Описание (RU)": d_ru_c if clean_html else d_ru_h
            }
            
            for idx, url in enumerate(img_list[:15]): row[f"Фото {idx+1}"] = url
            for k, v in c_ua.items():
                if k not in skip_list: row[f"{k} (UA)"] = v
            for k, v in c_ru.items():
                if k not in skip_list: row[f"{k} (RU)"] = v

            if not any(d['Артикул'] == sku for d in st.session_state.scraped_data):
                st.session_state.scraped_data.append(row)
            
            p_bar.progress((i + 1) / len(work_list))
            time.sleep(0.1)

        # Обновляем позицию для следующего раза
        st.session_state.next_start_node = min(end_at + 1, total_links)
        p_status.empty()
        st.rerun()

# --- Шаг 4 ---
if st.session_state.scraped_data:
    st.write("---")
    st.subheader("4. Результаты")
    df = pd.DataFrame(st.session_state.scraped_data)
    st.dataframe(df.head(5))
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Flagman', index=False)
    
    st.download_button(
        label=f"📥 Скачать Excel ({len(df)} товаров)",
        data=out.getvalue(),
        file_name="flagman_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
