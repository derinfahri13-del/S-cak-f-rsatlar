"""
Donanım Arşivi Forumu - Sıcak Fırsatlar Bot
Sadece RAM ve Fan/Soğutucu kategorisindeki indirim konularını tespit edip
e-posta ile bildirim gönderir.
"""

import os
import re
import json
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

FORUM_URL = "https://forum.donanimarsivi.com/forumlar/Sicakfirsatlar/"
SEEN_FILE = "seen_topics.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# Başlıkta aranacak anahtar kelimeler (küçük harfe çevrilip kontrol edilir)
RAM_KEYWORDS = [
    "ram", "bellek", "ddr3", "ddr4", "ddr5", "ryzen ram",
    "corsair vengeance", "kingston fury", "hyperx",
]
FAN_KEYWORDS = [
    "fan", "soğutucu", "sogutucu", "cooler", "cpu soğutucu",
    "kasa fanı", "kasa fani", "sıvı soğutma", "sivi sogutma",
    "aio", "watercooling", "hava soğutucu",
]

# Yanlış pozitifleri elemek için (başlıkta geçse de indirim/donanım
# konusuyla alakasız olabilecek kelimeler)
EXCLUDE_KEYWORDS = [
    "klavye", "mouse", "tansiyon", "kulaklık", "kulaklik",
    "telefon kılıf", "telefon kilif", "zeytinyağı", "zeytinyagi",
]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


def matches_category(title: str):
    t = title.lower()
    t = t.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace("ğ", "g")
    if any(bad in t for bad in EXCLUDE_KEYWORDS):
        return None
    for kw in RAM_KEYWORDS:
        if kw in t:
            return "RAM"
    for kw in FAN_KEYWORDS:
        if kw in t:
            return "Fan/Soğutucu"
    return None


def fetch_topics():
    resp = requests.get(FORUM_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    topics = []
    # XenForo 2 forum listesi: her konu bir <div class="structItem ...">
    items = soup.select("div.structItem--thread")
    for item in items:
        title_tag = item.select_one("div.structItem-title a[href*='/konu/']")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        href = title_tag.get("href", "")
        if href and not href.startswith("http"):
            href = "https://forum.donanimarsivi.com" + href

        # Konu id'sini linkten çıkar (örn: .../konu/baslik-adi.1234567/)
        m = re.search(r"\.(\d+)/?$", href.rstrip("/") + "/")
        topic_id = m.group(1) if m else href

        # "İndirim Bitti" ön ekli konuları atla
        prefix = ""
        prefix_tag = item.select_one("span.label")
        if prefix_tag:
            prefix = prefix_tag.get_text(strip=True)
        if "bitti" in prefix.lower():
            continue

        topics.append({"id": topic_id, "title": title, "url": href})

    return topics


def send_email(new_deals):
    smtp_user = os.environ["EMAIL_USER"]
    smtp_pass = os.environ["EMAIL_PASS"]
    to_addr = os.environ["EMAIL_TO"]

    subject = f"🔥 {len(new_deals)} yeni RAM/Fan fırsatı - Donanım Arşivi"

    body_lines = []
    for d in new_deals:
        body_lines.append(f"[{d['category']}] {d['title']}\n{d['url']}\n")
    body = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())


def main():
    seen = load_seen()
    first_run = len(seen) == 0

    try:
        topics = fetch_topics()
    except Exception as e:
        print(f"Forum çekilirken hata oluştu: {e}", file=sys.stderr)
        sys.exit(1)

    if not topics:
        print("Uyarı: Hiç konu bulunamadı, forum yapısı değişmiş olabilir.")
        sys.exit(0)

    new_deals = []
    current_ids = set()

    for t in topics:
        current_ids.add(t["id"])
        if t["id"] in seen:
            continue
        category = matches_category(t["title"])
        if category:
            new_deals.append({**t, "category": category})

    # İlk çalıştırmada mail atma, sadece mevcut konuları "görüldü" say
    # (aksi halde ilk seferde yüzlerce eski konu için mail gider)
    if first_run:
        print(f"İlk çalıştırma: {len(current_ids)} konu kayda alındı, mail gönderilmedi.")
        save_seen(current_ids)
        return

    seen |= current_ids

    if new_deals:
        print(f"{len(new_deals)} yeni RAM/Fan fırsatı bulundu, mail gönderiliyor...")
        send_email(new_deals)
    else:
        print("Yeni RAM/Fan fırsatı yok.")

    save_seen(seen)


if __name__ == "__main__":
    main()
