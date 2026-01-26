import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import random
import re
from io import BytesIO

st.set_page_config(page_title="Flagman Monitor Pro V4", page_icon="🎣", layout="wide")

# --- Инициализация состояния ---
if 'all_links' not in st.session_state:
    st.session_state.all_links = []
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'found_categories' not in st.session_state:
    st.session_state.found_categories = []
if 'last_pos' not in st.session_state:
    st.session_state.last_pos = 1

def get_soup(url, lang="uk"):
    cookies = {'i18n_redirected': lang}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9" if lang == "ru" else "uk-UA,uk;q=0.9"
    }
    try:
        session = requests.Session()
        r = session.get(url, headers=headers, cookies=cookies, timeout=20)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "lxml")
    except:
        return None
    return None

def parse_page_content(soup):
    if not soup: return "N/A", "N/A", "N/A", {}, {}
    product_json = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            js = json.loads(script.string)
            if isinstance(js, dict) and js.get("@type") == "Product":
                product_json = js
                break
        except: continue
    
    title = soup.find("h1").get_text(strip=True) if soup.find("h1") else product_json.get("name", "N/A")
    desc_block = soup.select_one(".product-description-text") or soup.select_one(".product-description__content")
    
    d_clean = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    d_html = desc_block.decode_contents().strip() if desc_block else ""
    
    chars = {}
    for ci in (soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")):
        p = ci.find_all("p")
        if len(p) >= 2:
            chars[p[0].get_text(strip=True)] = p[1].get_text(strip=True)
            
    return title, d_clean, d_html, chars, product_json

# --- Интерфейс ---
st.title("🎣 Flagman Smart Monitor Ultra")

with st.sidebar:
    if st.button("🗑 Очистить всё"):
        st.session_state.all_links = []
        st.session_state.scraped_data = []
        st.session_state.found_categories = []
        st.session_state.last_pos = 1
        st.rerun()

# Шаг 1 & 2
st.subheader("1. Подготовка ссылок")
c_u, c_p = st.columns([3, 1])
input_url = c_u.text_input("Ссылка на категорию")
p_limit = c_p.number_input("Стр. (0=все)", min_value=0, value=1)

if st.button("🔍 Найти подразделы"):
    base = input_url.replace("/ru/", "/")
    soup = get_soup(base)
    items = soup.select("a.item-link") if soup else []
    found = []
    for link in items:
        name = (link.select_one(".fish-title-mobile") or link).get_text(strip=True)
        href = link.get("href")
        if href and "/c" in href:
            if not href.startswith("http"): href = "https://flagman.ua" + href
            found.append({"name": name, "url": href.replace("/ru/", "/")})
    st.session_state.found_categories = found if found else [{"name": "Текущий раздел", "url": base}]

if st.session_state.found_categories:
    cat_map = {c['name']: c['url'] for c in st.session_state.found_categories}
    sel = st.multiselect("Мониторить разделы:", options=list(cat_map.keys()), default=list(cat_map.keys()))
    if st.button("🔎 Собрать ссылки на товары"):
        acc = []
        for n in sel:
            # Логика сбора ссылок
            links = []
            page = 1
            while True:
                if p_limit > 0 and page > p_limit: break
                url = f"{cat_map[n]}/page={page}" if page > 1 else cat_map[n]
                s = get_soup(url)
                if not s: break
                p_links = []
                for scr in s.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(scr.string)
                        if data.get("@type") == "ItemList":
                            for el in data.get("itemListElement", []):
                                u = el.get("item", {}).get("url")
                                if u: p_links.append(u)
                    except: continue
                if not p_links: break
                links.extend(p_links)
                page += 1
            acc.extend(links)
        st.session_state.all_links = list(dict.fromkeys(acc))
        st.rerun()

# Шаг 3
if st.session_state.all_links:
    st.subheader("2. Фильтры и Парсинг")
    skus_raw = st.text_area("Список Артикулов (через Enter):")
    clean_h = st.checkbox("Очищать HTML теги", value=True)
    
    target_skus = [x.strip() for x in re.split(r'[,\n\s]+', skus_raw) if x.strip()] if skus_raw else []
    total_q = len(st.session_state.all_links)
    
    st.info(f"📋 Очередь: {total_q} | 📍 Позиция: {st.session_state.last_pos} | ✅ Найдено: {len(st.session_state.scraped_data)}")

    # Форма
    with st.form("p_form"):
        c_f, c_c = st.columns(2)
        start_num = c_f.number_input("Начать с №", 1, total_q, value=st.session_state.last_pos)
        batch_size = c_c.number_input("Кол-во для проверки", 1, 2000, value=100)
        run_btn = st.form_submit_button("🚀 ЗАПУСТИТЬ ПАРСИНГ")

    if run_btn:
        work_links = st.session_state.all_links[int(start_num)-1 : int(start_num) + int(batch_size) - 1]
        p_bar = st.progress(0)
        p_status = st.empty()
        
        # Список ключей для пропуска
        skip = ["Код товару", "Код товара", "Артикул", "Артикул товару", "Виробник", "Производитель"]

        for i, link in enumerate(work_links):
            # Обновляем текст статуса только каждый 5-й товар, чтобы не уронить Streamlit
            if i % 5 == 0 or i == len(work_links)-1:
                p_status.write(f"⏳ Обработано {i} из {len(work_links)} товаров в этой пачке...")

            ua_url = link.replace("/ru/", "/")
            ru_url = link.replace("flagman.ua/", "flagman.ua/ru/")
            
            s_ua = get_soup(ua_url, "uk")
            if not s_ua: continue
            t_ua, d_ua_c, d_ua_h, c_ua, j_ua = parse_page_content(s_ua)
            sku = j_ua.get("sku", "N/A")

            if target_skus and sku not in target_skus:
                p_bar.progress((i + 1) / len(work_links))
                continue

            # Парсим RU версию
            s_ru = get_soup(ru_url, "ru")
            t_ru, d_ru_cl, d_ru_rw, c_ru, j_ru = parse_page_content(s_ru)
            
            # Фото
            imgs = [img.get('src') for img in s_ua.select(".product-images img") 
                    if img.get('src') and not img.get('src').startswith("data:")]
            
            row = {
                "Артикул": sku,
                "Бренд": j_ua.get("brand", {}).get("name", "N/A"),
                "Цена": j_ua.get("offers", {}).get("price", "N/A"),
                "Назва (UA)": t_ua, "Название (RU)": t_ru,
                "Опис (UA)": d_ua_c if clean_h else d_ua_h,
                "Описание (RU)": d_ru_cl if clean_h else d_ru_rw # ИСПРАВЛЕНО
            }
            for idx, url in enumerate(imgs[:15]): row[f"Фото {idx+1}"] = url
            
            # Добавляем характеристики, СТРОГО пропуская лишнее
            for k, v in c_ua.items():
                if k not in skip: row[f"{k} (UA)"] = v
            for k, v in c_ru.items():
                if k not in skip: row[f"{k} (RU)"] = v

            if not any(d['Артикул'] == sku for d in st.session_state.scraped_data):
                st.session_state.scraped_data.append(row)
            
            p_bar.progress((i + 1) / len(work_links))
            time.sleep(0.1)

        st.session_state.last_pos = min(int(start_num) + int(batch_size), total_q)
        st.success("Пачка готова!")
        st.rerun()

# Результаты
if st.session_state.scraped_data:
    df = pd.DataFrame(st.session_state.scraped_data)
    st.dataframe(df.head(10))
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Data', index=False)
    st.download_button(f"📥 Скачать Excel ({len(df)})", out.getvalue(), "report.xlsx")
