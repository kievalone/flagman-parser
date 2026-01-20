import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
from io import BytesIO

st.set_page_config(page_title="Flagman Parser Elite", page_icon="🎣")

# --- ФУНКЦИИ ПАРСИНГА ---

def get_soup(url, lang="uk"):
    cookies = {'i18n_redirected': lang}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9" if lang == "ru" else "uk-UA,uk;q=0.9"
    }
    try:
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            return BeautifulSoup(response.text, "lxml")
    except:
        return None

def get_subcategories_with_names(soup):
    """Ищет названия и ссылки на подкатегории"""
    sub_data = []
    # Ищем блоки категорий. Обычно это ссылки с классом item-link
    items = soup.select("a.item-link")
    for link in items:
        name_tag = link.select_one(".fish-title-mobile") or link.select_one(".category-name") or link
        name = name_tag.get_text(strip=True)
        href = link.get("href")
        if href and "/c" in href and name:
            if not href.startswith("http"):
                href = "https://flagman.ua" + href
            url = href.replace("/ru/", "/")
            sub_data.append({"name": name, "url": url})
    
    # Убираем дубликаты
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

# --- ИНТЕРФЕЙС STREAMLIT ---

st.title("🎣 Flagman Smart Monitor")

# Инициализация состояния
if 'categories' not in st.session_state:
    st.session_state.categories = []

input_url = st.text_input("Введите ссылку на категорию (главную или вложенную)", 
                         placeholder="https://flagman.ua/ru/kotushky/c166336")

col1, col2 = st.columns(2)
with col1:
    pages_limit = st.number_input("Страниц в каждом разделе (0 = все)", min_value=0, value=1)
with col2:
    btn_find = st.button("🔍 Найти категории / Проверить ссылку")

# Шаг 1: Поиск подкатегорий
if btn_find:
    if not input_url:
        st.error("Введите ссылку!")
    else:
        with st.spinner("Анализирую структуру сайта..."):
            base_url = input_url.replace("/ru/", "/")
            soup_main = get_soup(base_url)
            found_cats = get_subcategories_with_names(soup_main)
            
            if found_cats:
                st.session_state.categories = found_cats
                st.success(f"Найдено разделов: {len(found_cats)}")
            else:
                # Если подкатегорий нет, значит это прямая категория
                st.session_state.categories = [{"name": "Текущий раздел (без подкатегорий)", "url": base_url}]
                st.info("Вложенных разделов не найдено. Будет обработана текущая ссылка.")

# Шаг 2: Выбор и Запуск
if st.session_state.categories:
    st.write("### 📂 Выберите разделы для парсинга:")
    
    # Создаем словарь для мультиселекта
    cat_options = {c['name']: c['url'] for c in st.session_state.categories}
    selected_names = st.multiselect("Выберите нужные:", 
                                   options=list(cat_options.keys()), 
                                   default=list(cat_options.keys()))

    if st.button("🚀 ЗАПУСТИТЬ МОНИТОРИНГ"):
        if not selected_names:
            st.warning("Выберите хотя бы одну категорию!")
        else:
            final_data = []
            skip_keys = ["Код товару", "Код товара", "Артикул", "Артикул товару"]
            
            total_selected = len(selected_names)
            
            for c_idx, name in enumerate(selected_names):
                cat_url = cat_options[name]
                st.write(f"---")
                st.write(f"📦 **Раздел [{c_idx+1}/{total_selected}]: {name}**")
                
                # Собираем ссылки на товары
                status_text = st.empty()
                status_text.write("🔎 Сбор ссылок на товары...")
                product_links = get_product_links(cat_url, None if pages_limit == 0 else pages_limit)
                
                if not product_links:
                    st.write("❌ В этом разделе товаров нет.")
                    continue
                
                total_links = len(product_links)
                st.write(f"✅ Найдено товаров: {total_links}")
                
                # Парсим каждый товар
                bar = st.progress(0)
                item_status = st.empty()
                
                for i, link in enumerate(product_links):
                    # Показываем счетчик
                    item_status.write(f"🔹 Обработка товара **{i+1} из {total_links}**")
                    
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
                    
                    image_urls = [img.get('src') for img in soup_ua.select(".product-images img") if img.get('src')]
                    
                    row = {
                        "Артикул": sku,
                        "Бренд": brand,
                        "Цена": price,
                        "Категория": name,
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
                    
                    # Обновляем прогресс-бар
                    bar.progress((i + 1) / total_links)
                    time.sleep(0.3)
                
                item_status.empty()

            if final_data:
                df = pd.DataFrame(final_data)
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Flagman Data', index=False)
                
                st.balloons()
                st.success(f"💎 ВСЁ ГОТОВО! Собрано товаров: {len(final_data)}")
                st.download_button(
                    label="📥 СКАЧАТЬ EXCEL ТАБЛИЦУ",
                    data=output.getvalue(),
                    file_name="flagman_full_monitoring.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
