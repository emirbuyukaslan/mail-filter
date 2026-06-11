"""
Mail süzgeci otomasyonu (Gmail IMAP + Uygulama Şifresi).

Akış:
  1. Gmail'e IMAP ile (uygulama şifresi) bağlan, okunmamış mailleri çek.
  2. Her maili Gemini API'ye gönder -> özet + önem skoru (1-5) al.
  3. Skor eşiği aşıyorsa Telegram'dan bildirim gönder.
  4. İşlenen mailleri state dosyasına yaz ki tekrar bildirim gitmesin.

Google Cloud / Gmail API gerekmez. Sadece Google hesabında 2 Adımlı Doğrulama
açıp bir "Uygulama Şifresi" (App Password) üretip .env'e koyman yeterli.

Kullanım:
  python mail_filter.py
  python mail_filter.py --dry-run   # bildirim göndermeden test et
"""

from __future__ import annotations

import argparse
import email
import html
import imaplib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "processed.json"
LOG_FILE = BASE_DIR / "mail_filter.log"

load_dotenv(BASE_DIR / ".env")

# Windows konsolu Türkçe karakterlerde çökmesin diye stdout'u UTF-8'e çevir
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # pythonw ile çalışırken stdout None olabilir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mail_filter")


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #
def env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if val is not None:
        val = val.strip()  # baştaki/sondaki boşlukları temizle (örn. "= AIza...")
    if required and not val:
        log.error("Eksik ayar: %s (.env dosyasını kontrol et)", key)
        sys.exit(1)
    return val or ""


# --------------------------------------------------------------------------- #
# State (tekrar bildirim önleme)
# --------------------------------------------------------------------------- #
def load_state() -> set[str]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_state(processed: set[str]) -> None:
    # Kararlı (sıralı) yazım: içerik değişmedikçe dosya birebir aynı kalır ->
    # bulutta gereksiz "state" commit'leri olmaz. sorted ayrıca set'in rastgele
    # sırasını sabitler. Son 2000 kayıtla sınırla ki dosya şişmesin.
    trimmed = sorted(processed)[-2000:]
    STATE_FILE.write_text(json.dumps(trimmed, indent=0), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Gmail IMAP — uygulama şifresi ile bağlanma
# --------------------------------------------------------------------------- #
def decode_header_value(value: str | None) -> str:
    """MIME ile kodlanmış başlıkları (Türkçe karakter vs.) düz metne çevir."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def get_body(msg: email.message.Message) -> str:
    """Mailin düz metin gövdesini çıkar; sadece HTML varsa kabaca temizle."""
    def extract(part):
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                return ""
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        except Exception:
            return ""

    text, html = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and not text:
                text = extract(part)
            elif ctype == "text/html" and not html:
                html = extract(part)
    else:
        if msg.get_content_type() == "text/html":
            html = extract(msg)
        else:
            text = extract(msg)

    if text:
        return text.strip()
    if html:
        stripped = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", stripped).strip()
    return ""


def fetch_emails():
    host = env("IMAP_HOST", "imap.gmail.com")
    port = int(env("IMAP_PORT", "993"))
    user = env("IMAP_USER", required=True)
    password = env("IMAP_PASSWORD", required=True).replace(" ", "")  # app password boşluksuz
    folder = env("IMAP_FOLDER", "INBOX")
    search = env("IMAP_SEARCH", "UNSEEN").upper()
    lookback = int(env("LOOKBACK_DAYS", "2"))

    log.info("IMAP bağlanılıyor: %s@%s", user, host)
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
    except imaplib.IMAP4.error as e:
        log.error(
            "IMAP giriş başarısız: %s — Uygulama Şifresi doğru mu? "
            "(normal şifre çalışmaz, 2 Adımlı Doğrulama açık olmalı)",
            e,
        )
        sys.exit(1)
    imap.select(folder)

    since = (datetime.now() - timedelta(days=lookback)).strftime("%d-%b-%Y")
    criteria = f"(SINCE {since})" if search == "ALL" else f"({search} SINCE {since})"
    typ, data = imap.search(None, criteria)
    if typ != "OK":
        log.warning("IMAP search başarısız: %s", typ)
        imap.logout()
        return []

    ids = data[0].split()
    log.info("%d mail bulundu (kriter: %s)", len(ids), criteria)

    emails = []
    for num in ids:
        # PEEK -> maili okundu olarak işaretlemeden çek
        typ, msg_data = imap.fetch(num, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        msg_id = decode_header_value(msg.get("Message-ID")) or f"{folder}:{num.decode()}"
        emails.append(
            {
                "uid": msg_id,
                "from": decode_header_value(msg.get("From")),
                "subject": decode_header_value(msg.get("Subject")) or "(konu yok)",
                "date": decode_header_value(msg.get("Date")),
                "body": get_body(msg)[:6000],  # token tasarrufu
            }
        )

    imap.logout()
    return emails


# --------------------------------------------------------------------------- #
# Gemini ile özet + önem (ücretsiz katman, REST API)
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """Sen bir e-posta asistanısın. Verilen e-postayı analiz et ve
Türkçe yanıt ver.

Önem skoru (importance) rehberi:
5 = Acil, hemen aksiyon gerekir (son tarih bugün, kritik sorun, patron/müşteri acil)
4 = Önemli, yakında aksiyon gerekir (toplantı, fatura, kişisel önemli mesaj)
3 = Dikkate değer ama acil değil
2 = Bilgilendirme, aksiyon gerekmez
1 = Bülten, reklam, otomatik bildirim, spam"""

# Gemini'nin çıktıyı garanti-JSON üretmesi için şema
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "importance": {"type": "integer"},
        "reason": {"type": "string"},
        "category": {"type": "string"},
        "action_needed": {"type": "boolean"},
    },
    "required": ["summary", "importance", "reason", "category", "action_needed"],
}


# Ardışık istekler arasında en az bu kadar saniye bekle (ücretsiz katman: 15 istek/dk).
# REQUESTS_PER_MINUTE=14 -> ~4.3 sn aralık, güvenli marj.
_RPM = max(1, int(env("REQUESTS_PER_MINUTE", "14")))
_MIN_INTERVAL = 60.0 / _RPM
_last_call_at = 0.0


def _throttle():
    """Hız limitine takılmamak için istekler arasını açar."""
    global _last_call_at
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def _parse_retry_delay(text: str) -> float:
    """429 yanıtındaki 'retryDelay' (örn. '53s') değerini saniye olarak çıkar."""
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', text)
    if m:
        return float(m.group(1)) + 1.0
    m = re.search(r"retry in ([\d.]+)s", text)
    return (float(m.group(1)) + 1.0) if m else 30.0


def analyze(api_key: str, model: str, mail: dict, max_retries: int = 3) -> dict:
    content = (
        f"Kimden: {mail['from']}\n"
        f"Konu: {mail['subject']}\n"
        f"Tarih: {mail['date']}\n\n"
        f"İçerik:\n{mail['body']}"
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": content}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 0.2,
        },
    }
    for attempt in range(max_retries):
        _throttle()
        r = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if r.status_code == 200:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        if r.status_code == 429 and attempt < max_retries - 1:
            delay = _parse_retry_delay(r.text)
            log.warning("Kota limiti — %.0f sn bekleniyor (deneme %d/%d)...",
                        delay, attempt + 1, max_retries)
            time.sleep(delay)
            continue
        raise RuntimeError(f"Gemini hatası {r.status_code}: {r.text[:200]}")
    raise RuntimeError("Gemini: tekrar denemeler tükendi (kota)")


# --------------------------------------------------------------------------- #
# Telegram bildirimi
# --------------------------------------------------------------------------- #
def send_telegram(text: str) -> bool:
    token = env("TELEGRAM_BOT_TOKEN", required=True)
    chat_id = env("TELEGRAM_CHAT_ID", required=True)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if r.status_code != 200:
            log.error("Telegram hatası %s: %s", r.status_code, r.text)
            return False
        return True
    except Exception as e:
        log.error("Telegram gönderilemedi: %s", e)
        return False


def format_notification(mail: dict, analysis: dict) -> str:
    stars = "⭐" * int(analysis.get("importance", 0))
    action = "🔴 Aksiyon gerekli" if analysis.get("action_needed") else "🟢 Bilgi"
    sender = parseaddr(mail["from"])
    sender_str = f"{sender[0]} <{sender[1]}>" if sender[0] else sender[1] or mail["from"]

    # Telegram HTML modunda <, >, & karakterleri etiket sanılır -> escape şart
    def esc(value) -> str:
        return html.escape(str(value))

    return (
        f"<b>📬 Önemli Mail</b> {stars}\n"
        f"<b>Kimden:</b> {esc(sender_str)}\n"
        f"<b>Konu:</b> {esc(mail['subject'])}\n"
        f"<b>Kategori:</b> {esc(analysis.get('category', '-'))} | {action}\n\n"
        f"<b>Özet:</b> {esc(analysis.get('summary', '-'))}\n\n"
        f"<i>{esc(analysis.get('reason', ''))}</i>"
    )


# --------------------------------------------------------------------------- #
# Ana akış
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Mail süzgeci (Gmail IMAP)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Telegram göndermeden çalıştır (terminale yazar)",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Mevcut mailleri 'görüldü' işaretle (Gemini/Telegram yok). Sıfırdan başlamak için.",
    )
    args = parser.parse_args()

    threshold = int(env("IMPORTANCE_THRESHOLD", "3"))
    model = env("GEMINI_MODEL", "gemini-2.0-flash")
    api_key = "" if args.seed else env("GEMINI_API_KEY", required=True)

    processed = load_state()
    emails = fetch_emails()

    # --seed: hiç analiz/bildirim yapma, hepsini görüldü say ve çık.
    if args.seed:
        for mail in emails:
            processed.add(mail["uid"])
        save_state(processed)
        log.info(
            "Seed tamam: %d mevcut mail 'görüldü' olarak işaretlendi. "
            "Bundan sonra sadece yeni mailler bildirilecek.",
            len(emails),
        )
        return

    new_count = notified = 0
    for mail in emails:
        if mail["uid"] in processed:
            continue
        new_count += 1
        try:
            analysis = analyze(api_key, model, mail)
        except Exception as e:
            log.error("Analiz hatası (%s): %s", mail["subject"], e)
            continue

        importance = int(analysis.get("importance", 0))
        log.info(
            "[%s/5] %s — %s",
            importance,
            mail["subject"][:60],
            analysis.get("summary", "")[:80],
        )

        if importance >= threshold:
            text = format_notification(mail, analysis)
            if args.dry_run:
                print("\n--- BİLDİRİM (dry-run) ---\n" + text + "\n")
                notified += 1
            elif send_telegram(text):
                notified += 1
                log.info("  -> Telegram bildirimi gönderildi")

        processed.add(mail["uid"])

    if not args.dry_run:
        save_state(processed)

    log.info(
        "Bitti. Yeni mail: %d, bildirim: %d, eşik: %d", new_count, notified, threshold
    )


if __name__ == "__main__":
    main()
