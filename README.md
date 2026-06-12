# Mail Süzgeci 📬

Gelen mailleri **Google Gemini (ücretsiz)** ile özetler, **önemli** olanlar için Telegram bildirimi gönderir.
Gmail'e **IMAP + Uygulama Şifresi** ile bağlanır (Google Cloud gerekmez). **Bulutta (GitHub Actions)
7/24 otomatik çalışır** — bilgisayar kapalıyken bile. Tamamen ücretsiz.

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

### 4. Düzenli tetikleme (cron-job.org) — önerilen
GitHub'ın yerleşik `schedule` (cron) tetikleyicisi **güvenilmezdir** — özel repolarda saatlerce
gecikebilir/atlanabilir. GitHub API ile gönderilen **dispatch** tetiklemeleri ise kısılmaz, zamanında
çalışır. Bu yüzden düzenli çalışma için ücretsiz bir dış cron kullanılır:

1. **Fine-grained GitHub token** oluştur: https://github.com/settings/personal-access-tokens/new
   - Repository access → sadece bu repo
   - Permissions → **Actions: Read and write** (Metadata: Read otomatik)
2. [cron-job.org](https://cron-job.org) (ücretsiz) → yeni cronjob:
   - **URL:** `https://api.github.com/repos/<kullanici>/<repo>/actions/workflows/mail-filter.yml/dispatches`
   - **Method:** `POST`
   - **Headers:** `Authorization: Bearer <token>` · `Accept: application/vnd.github+json` · `X-GitHub-Api-Version: 2022-11-28`
   - **Body:** `{"ref":"main"}`
   - **Schedule:** her 10 dk (istediğin sıklık)
   - Test run → **204** dönerse çalışıyor.

> `.github/workflows/mail-filter.yml` içindeki yerleşik `schedule` (10 dk) **yedek** olarak kalır.
> Token'ın son kullanma tarihi gelince yenileyip cron-job.org'da güncellemen yeterli.

### 5. Görünürlük ve gizlilik
- **Public repo:** Actions dakikaları sınırsız + schedule biraz daha düzenli + linki paylaşabilirsin.
  Ancak Actions **logları herkese açıktır** — bu yüzden kod, mail konusu/özetini loglara **yazmaz**
  (sadece Telegram'a gider). Yerelde ayrıntılı log istersen `.env`'e `VERBOSE_LOG=true` ekle.
- **Private repo:** Loglar gizli, ücretsiz Actions kotası ayda 2000 dk (15 dk'da kotayı aşar → 30 dk'ya çek).
- Her iki durumda da **sırlar Secrets'ta şifrelidir**, logda `***` maskelenir, repoda görünmez.

### 6. Yerel görevi kaldır (buluta geçtikten sonra)
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
| `GEMINI_MODEL` | Gemini modeli (örn. `gemini-3.1-flash-lite`, `gemini-2.5-flash`) | gemini-3.1-flash-lite |
| `IMPORTANCE_THRESHOLD` | Kaç ve üstü skor "önemli" sayılsın (1-5) | `3` |
| `REQUESTS_PER_MINUTE` | Gemini hız sınırı (ücretsiz katman 15/dk) | `14` |
| `VERBOSE_LOG` | Mail konusu/özetini de logla (gizlilik için bulutta `false`) | `false` |

---

## Sorun giderme

- **Loglar:** `mail_filter.log`
- **IMAP giriş başarısız:** Mutlaka *Uygulama Şifresi* kullan (normal şifre çalışmaz). 2 Adımlı Doğrulama açık olmalı. Gmail → Ayarlar → "Yönlendirme ve POP/IMAP" → IMAP'in açık olduğundan emin ol.
- **Telegram gelmiyor:** Önce bota bir kez mesaj atmış olman gerekir; chat id'yi `getUpdates` ile doğrula.
- **Görevi kaldır:** `Unregister-ScheduledTask -TaskName MailFilter -Confirm:$false`
- **Hemen çalıştır:** `Start-ScheduledTask -TaskName MailFilter`
