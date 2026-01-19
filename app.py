import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import time
from io import BytesIO

# Настройки страницы
st.set_page_config(page_title="Flagman Parser", page_icon="🎣")

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

def get_product_links(cat_url, lang, max_pages):
    links = []
    page = 1
    while True:
        if max_pages and page > max_pages: break
        page_url = f"{cat_url}/page={page}" if page > 1 else cat_url
        soup = get_soup(page_url, lang=lang)
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

def get_product_details(url, lang):
    soup = get_soup(url, lang=lang)
    if not soup: return None
    
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

    item = {
        "Название" if lang == "ru" else "Назва": title,
        "Артикул": product_json.get("sku"),
        "Цена" if lang == "ru" else "Ціна": product_json.get("offers", {}).get("price"),
        "Описание" if lang == "ru" else "Опис": description,
        "Фото": " ".join([img.get('src') for img in soup.select(".product-images img") if img.get('src')]),
        "Ссылка": url
    }

    for char in (soup.select(".chars-items-wrapper .chars-item") or soup.select(".product-properties__item")):
        names = char.find_all("p")
        if len(names) >= 2:
            item[names[0].get_text(strip=True)] = names[1].get_text(strip=True)
    return item

# --- ИНТЕРФЕЙС СТРИМЛИТ ---
st.title("🎣 Flagman Parser PRO")
st.write("Введите ссылку на категорию, и я соберу данные для UA и RU версий.")

input_url = st.text_input("Ссылка на категорию", placeholder="https://flagman.ua/...")
pages_limit = st.number_input("Кол-во страниц (0 = все)", min_value=0, value=1)

if st.button("Начать парсинг"):
    if not input_url:
        st.error("Введите ссылку!")
    else:
        # Логика ссылок
        ua_url = input_url.replace("/ru/", "/")
        ru_url = input_url if "/ru/" in input_url else input_url.replace("flagman.ua/", "flagman.ua/ru/")
        max_p = None if pages_limit == 0 else pages_limit

        with st.status("Работаю...", expanded=True) as status:
            st.write("Собираю ссылки...")
            links_ua = get_product_links(ua_url, "uk", max_p)
            links_ru = get_product_links(ru_url, "ru", max_p)
            
            all_links = list(set(links_ua + links_ru))
            st.write(f"Найдено товаров: {len(all_links)}")
            
            data_ua, data_ru = [], []
            progress_bar = st.progress(0)
            
            for i, link in enumerate(all_links):
                # Для UA
                d_ua = get_product_details(link.replace("/ru/", "/"), "uk")
                if d_ua: data_ua.append(d_ua)
                # Для RU
                d_ru = get_product_details(link if "/ru/" in link else link.replace("flagman.ua/", "flagman.ua/ru/"), "ru")
                if d_ru: data_ru.append(d_ru)
                
                progress_bar.progress((i + 1) / len(all_links))
                time.sleep(0.5)

            status.update(label="Парсинг завершен!", state="complete")

        # Создание Excel в памяти
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(data_ua).to_excel(writer, sheet_name='UA', index=False)
            pd.DataFrame(data_ru).to_excel(writer, sheet_name='RU', index=False)
        
        st.success("Таблица готова!")
        st.download_button(
            label="📥 Скачать Excel результат",
            data=output.getvalue(),
            file_name="flagman_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
