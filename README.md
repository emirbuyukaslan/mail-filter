# Mail Süzgeci 📬

Gelen mailleri **Google Gemini (ücretsiz)** ile özetler, **önemli** olanlar için Telegram bildirimi gönderir.
Gmail'e **IMAP + Uygulama Şifresi** ile bağlanır (Google Cloud gerekmez), Windows Task Scheduler ile periyodik çalışır.
Tamamen ücretsiz çalışır.

## Nasıl çalışır?

```
Gmail (IMAP) → okunmamış mailler → Gemini (özet + önem 1-5) → eşik üstüyse → Telegram
```

İşlenen mailler `processed.json`'a kaydedilir, aynı mail iki kez bildirilmez.
Mailler okundu olarak **işaretlenmez** (BODY.PEEK).

İki şekilde çalıştırılabilir:
- **Bulut (GitHub Actions):** Bilgisayar kapalıyken de 7/24 çalışır. → [Bulut kurulumu](#bulut-kurulumu-github-actions-7-24)
- **Yerel (Windows):** Bilgisayar açıkken çalışır. → [Yerel kurulum](#kurulum)

---

## Bulut kurulumu (GitHub Actions, 7/24)

Otomasyon bulutta çalışır; bilgisayarın kapalı olsa bile mailler kontrol edilir. Ücretsiz.

### 1. Repoyu GitHub'a yükle
Bu klasör bir git deposu. **private** bir GitHub reposu oluştur ve push'la:
```powershell
git remote add origin https://github.com/<kullanici>/<repo>.git
git push -u origin main
```
> `.env` dosyası `.gitignore`'da — repoya **gitmez**. Sırlar aşağıda Secrets olarak girilir.

### 2. Secrets gir
GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
Şu 5 secret'ı ekle (değerleri `.env`'inden al):

| Secret adı | Değer |
|------------|-------|
| `IMAP_USER` | Gmail adresin |
| `IMAP_PASSWORD` | 16 haneli uygulama şifresi |
| `GEMINI_API_KEY` | Gemini API anahtarı |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat id |

Diğer ayarlar (`GEMINI_MODEL`, `IMPORTANCE_THRESHOLD`, `LOOKBACK_DAYS` vb.) gizli olmadığı için
`.github/workflows/mail-filter.yml` içinde `env:` altında durur; oradan düzenleyebilirsin.

### 3. Test et
Repo → **Actions** sekmesi → "Mail Filter" → **Run workflow**. Koşu yeşil olmalı, logda
`Bitti. Yeni mail: ...` satırı görünmeli. Yeni önemli mail varsa Telegram'a düşer.

### 4. Çalışma sıklığı
Varsayılan **30 dakikada bir** (`.github/workflows/mail-filter.yml` → `cron`).
- Private repo ücretsiz Actions kotası ayda 2000 dk; 30 dk güvenli.
- Daha sık (örn. 15 dk) istiyorsan repoyu **public** yap (Actions dakikaları sınırsız olur, kod görünür olur).

### 5. Yerel görevi kaldır (buluta geçtikten sonra)
```powershell
Unregister-ScheduledTask -TaskName MailFilter -Confirm:$false
```

---

## Kurulum
> Aşağısı **yerel** (Windows) çalıştırma içindir. Bulut kullanıyorsan bu bölüme gerek yok.

### 1. Python paketleri
```powershell
pip install -r requirements.txt
```

### 2. Gmail Uygulama Şifresi (App Password)
Google Cloud YOK. Sadece şunlar:
1. **2 Adımlı Doğrulamayı aç:** https://myaccount.google.com/signinoptions/twosv
2. **Uygulama şifresi üret:** https://myaccount.google.com/apppasswords
   - "Mail" + "Windows Computer" seç → **16 haneli şifreyi** kopyala.
   - Bu, normal şifren DEĞİL; sadece bu uygulama için, istediğin an iptal edilebilir.
3. Bu şifreyi `.env` içindeki `IMAP_PASSWORD=` satırına yapıştır, `IMAP_USER=` kısmına Gmail adresini yaz.

### 3. Gemini API anahtarı (ücretsiz)
https://aistudio.google.com/apikey → **Create API key** (kredi kartı gerekmez) → `.env`'deki `GEMINI_API_KEY=` satırına yapıştır.

> **Gemini Plus/Advanced aboneliği ≠ API key.** Abonelik Gemini *uygulaması* içindir; API anahtarı ayrı ve ücretsizdir.

### 4. Telegram
- **Bot token:** Telegram'da @BotFather → `/newbot`
- **Chat id:** botuna bir mesaj at → `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`

### 5. Test et (bildirim göndermeden)
```powershell
python mail_filter.py --dry-run
```
Önemli sayılan mailler terminale yazılır. Doğruysa gerçek çalıştır:
```powershell
python mail_filter.py
```

### 6. Zamanlanmış çalıştırma
```powershell
PowerShell -ExecutionPolicy Bypass -File .\setup_scheduler.ps1
```
Varsayılan **15 dakikada bir**. Farklı aralık: `-IntervalMinutes 5`

---

## Ayarlar (.env)

| Anahtar | Açıklama | Varsayılan |
|---------|----------|-----------|
| `IMAP_USER` / `IMAP_PASSWORD` | Gmail adresi + 16 haneli uygulama şifresi | — |
| `IMAP_SEARCH` | `UNSEEN` (okunmamışlar) veya `ALL` | `UNSEEN` |
| `LOOKBACK_DAYS` | Kaç gün geriye bakılsın | `2` |
| `GEMINI_MODEL` | `gemini-2.0-flash` (ücretsiz, hızlı) / `gemini-2.5-flash` | gemini-2.0-flash |
| `IMPORTANCE_THRESHOLD` | Kaç ve üstü skor "önemli" sayılsın (1-5) | `3` |

---

## Sorun giderme

- **Loglar:** `mail_filter.log`
- **IMAP giriş başarısız:** Mutlaka *Uygulama Şifresi* kullan (normal şifre çalışmaz). 2 Adımlı Doğrulama açık olmalı. Gmail → Ayarlar → "Yönlendirme ve POP/IMAP" → IMAP'in açık olduğundan emin ol.
- **Telegram gelmiyor:** Önce bota bir kez mesaj atmış olman gerekir; chat id'yi `getUpdates` ile doğrula.
- **Görevi kaldır:** `Unregister-ScheduledTask -TaskName MailFilter -Confirm:$false`
- **Hemen çalıştır:** `Start-ScheduledTask -TaskName MailFilter`
