import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
import random
from io import BytesIO

st.set_page_config(page_title="Flagman Pro Ultra", page_icon="🎣", layout="wide")

# --- Память сессии ---
if 'all_links' not in st.session_state:
    st.session_state.all_links = []
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'found_categories' not in st.session_state:
    st.session_state.found_categories = []

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
    
    # Название
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else product_json.get("name", "N/A")
    
    # Описание
    desc_block = soup.select_one(".product-description-text") or soup.select_one(".product-description__content")
    description = desc_block.get_text(separator="\n", strip=True) if desc_block else ""
    
    # Характеристики
    chars = {}
    char_items = soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")
    for ci in char_items:
        p_tags = ci.find_all("p")
        if len(p_tags) >= 2:
            chars[p_tags[0].get_text(strip=True)] = p_tags[1].get_text(strip=True)
            
    return title, description, chars, product_json

# --- Интерфейс ---

st.title("🎣 Flagman Smart Monitor Pro")

with st.sidebar:
    st.header("Управление данными")
    if st.button("🗑 Очистить память и ссылки"):
        st.session_state.all_links = []
        st.session_state.scraped_data = []
        st.session_state.found_categories = []
        st.rerun()

st.subheader("1. Настройка категории")
col_url, col_pg = st.columns([3, 1])
with col_url:
    input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/ru/kotushky/c166336")
with col_pg:
    pages_limit = st.number_input("Стр. в разделе (0=все)", min_value=0, value=1)

if st.button("🔍 Проверить разделы"):
    if input_url:
        with st.spinner("Анализ..."):
            base_url = input_url.replace("/ru/", "/")
            soup_main = get_soup(base_url)
            found = get_subcategories_with_names(soup_main)
            st.session_state.found_categories = found if found else [{"name": "Текущий раздел", "url": base_url}]
            st.rerun()

if st.session_state.found_categories:
    st.subheader("2. Выбор категорий")
    cat_map = {c['name']: c['url'] for c in st.session_state.found_categories}
    selected_cat_names = st.multiselect("Мониторить подразделы:", options=list(cat_map.keys()), default=list(cat_map.keys()))
    
    if st.button("🔎 Собрать список товаров"):
        all_p_links = []
        with st.status("Сбор ссылок...") as s:
            for name in selected_cat_names:
                st.write(f"Сканирую: {name}")
                links = get_product_links(cat_map[name], None if pages_limit == 0 else pages_limit)
                all_p_links.extend(links)
            st.session_state.all_links = list(dict.fromkeys(all_p_links))
            s.update(label=f"Найдено ссылок: {len(st.session_state.all_links)}", state="complete")
        st.rerun()

if st.session_state.all_links:
    total = len(st.session_state.all_links)
    done = len(st.session_state.scraped_data)
    
    st.subheader("3. Запуск парсинга")
    st.info(f"В очереди: {total} | Готово: {done}")
    
    col_from, col_count, col_go = st.columns([1, 1, 2])
    with col_from:
        start_idx = st.number_input("Начать с №", min_value=1, max_value=total, value=done + 1)
    with col_count:
        batch_size = st.number_input("Кол-во для этой пачки", min_value=1, max_value=200, value=20)
    
    if col_go.button("🚀 ПАРСИТЬ ПАЧКУ"):
        end_idx = min(start_idx + batch_size - 1, total)
        work_links = st.session_state.all_links[start_idx-1 : end_idx]
        
        bar = st.progress(0)
        status_info = st.empty()
        
        # Список ключей для удаления из характеристик
        skip_keys = [
            "Код товару", "Код товара", "Артикул", "Артикул товару", 
            "Виробник", "Производитель" # Убираем дубли производителей
        ]

        for i, link in enumerate(work_links):
            current_num = start_idx + i
            status_info.write(f"🔹 Товар **{current_num} из {total}** | Обрабатываем...")
            
            ua_link = link.replace("/ru/", "/")
            ru_link = link.replace("flagman.ua/", "flagman.ua/ru/")
            
            soup_ua = get_soup(ua_link, "uk")
            time.sleep(0.1)
            soup_ru = get_soup(ru_link, "ru")
            
            t_ua, d_ua, c_ua, j_ua = parse_page_content(soup_ua)
            t_ru, d_ru, c_ru, j_ru = parse_page_content(soup_ru)
            
            sku = j_ua.get("sku", "N/A")
            brand = j_ua.get("brand", {}).get("name", "N/A")
            
            # Чистим ссылки на фото от мусора (data:image и прочее)
            img_tags = soup_ua.select(".product-images img")
            clean_image_urls = []
            for img in img_tags:
                src = img.get('src')
                if src and not src.startswith("data:image"):
                    clean_image_urls.append(src)
            
            # Если в блоке пусто, пробуем мета-тег (главное фото)
            if not clean_image_urls:
                og_image = soup_ua.find("meta", property="og:image")
                if og_image: clean_image_urls.append(og_image["content"])
            
            row = {
                "Артикул": sku,
                "Бренд": brand,
                "Цена": j_ua.get("offers", {}).get("price", "N/A"),
                "Назва (UA)": t_ua,
                "Название (RU)": t_ru,
                "Опис (UA)": d_ua,
                "Описание (RU)": d_ru  # ИСПРАВЛЕНО: было t_ru
            }
            
            # Раскладываем фото
            for idx, img_url in enumerate(clean_image_urls[:15]): 
                row[f"Фото {idx+1}"] = img_url
            
            # Характеристики без лишних колонок
            for k, v in c_ua.items():
                if k not in skip_keys: row[f"{k} (UA)"] = v
            for k, v in c_ru.items():
                if k not in skip_keys: row[f"{k} (RU)"] = v

            row["Ссылка (UA)"] = ua_link
            row["Ссылка (RU)"] = ru_link

            # Обновляем или добавляем в список
            if not any(d['Артикул'] == sku for d in st.session_state.scraped_data):
                st.session_state.scraped_data.append(row)
            
            bar.progress((i + 1) / len(work_links))
            time.sleep(random.uniform(0.6, 1.2))

        status_info.empty()
        st.rerun()

if st.session_state.scraped_data:
    st.subheader("4. Результаты")
    df = pd.DataFrame(st.session_state.scraped_data)
    st.dataframe(df.head(5))
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Flagman_Combined', index=False)
    
    st.download_button(
        label=f"📥 Скачать Excel ({len(st.session_state.scraped_data)} товаров)",
        data=output.getvalue(),
        file_name="flagman_data_combined.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
