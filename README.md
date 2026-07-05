# USTALRTOSHKENT Bot

## Bot nima qiladi
1. Kalit so'zlar bo'yicha ochiq qurilish/ustachilik guruhlarini qidirib, sekin-asta qo'shiladi.
2. Bot ishga tushgandan **keyingi** yangi xabarlarnigina tahlil qiladi (eski xabarlarga tegmaydi).
3. Claude AI orqali xabar ustachilik ishi (gipsokarton, kafel, elektrik va h.k.) ekanini tekshiradi.
4. Mos kelsa:
   - Telefon raqami **bor** bo'lsa -> xabar o'zgarishsiz `@USTALRTOSHKENT` ga joylanadi.
   - Telefon raqami **yo'q** bo'lsa -> xabar matni + yozgan odamning username'i birga joylanadi.

## Lokal test qilish

```bash
pip install -r requirements.txt
```

Environment variables (`.env` fayl yoki terminalda export qiling):

```
TG_API_ID=123456
TG_API_HASH=abcdef1234567890
ANTHROPIC_API_KEY=sk-ant-...
TARGET_CHANNEL=@USTALRTOSHKENT
```

Birinchi marta ishga tushirganda Telethon telefon raqam va kod so'raydi
(agar SESSION_STRING berilmagan bo'lsa):

```bash
python bot.py
```

## Render.com'ga deploy qilish

### 1-qadam: StringSession yarating (faqat bir marta, o'z kompyuteringizda)
```bash
pip install telethon
python generate_session.py
```
Chiqqan uzun matnni saqlab qo'ying - bu `SESSION_STRING` bo'ladi.

### 2-qadam: Render.com'da servis yaratish
- render.com -> New + -> **Background Worker**
- GitHub repositoriyangizni ulang
- Sozlamalar:
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `python bot.py`

### 3-qadam: Environment Variables qo'shish (Render dashboard -> Environment)
| Nomi | Qiymati |
|---|---|
| `TG_API_ID` | my.telegram.org dan olingan ID |
| `TG_API_HASH` | my.telegram.org dan olingan hash |
| `SESSION_STRING` | generate_session.py chiqargan matn |
| `ANTHROPIC_API_KEY` | Claude API kaliti |
| `TARGET_CHANNEL` | `@USTALRTOSHKENT` |

### 4-qadam: Deploy
"Create Background Worker" tugmasini bosing - bot avtomatik ishga tushadi.

## Muhim ogohlantirishlar
- Bu **userbot** (shaxsiy akkaunt orqali ishlaydi), rasmiy Bot API emas -
  shuning uchun ko'p guruhga tez qo'shilish yoki tez-tez xabar yozish
  akkauntni **vaqtincha yoki butunlay bloklashi** mumkin. Kodda buning oldini
  olish uchun kutish (delay) va limitlar qo'yilgan - ularni kamaytirmang.
- Odamlarning username/kontaktini ularning roziligisiz kanalga chiqarish
  shaxsiy ma'lumotlarni himoya qilish nuqtai nazaridan ehtiyotkorlik talab
  qiladi. Faqat ochiq guruhlarda ochiq joylangan e'lonlar uchun ishlating.
- `MAX_GROUPS_PER_RUN` va `JOIN_DELAY_SECONDS` qiymatlarini `bot.py` faylida
  o'zingiz sozlashingiz mumkin (xavfsizroq bo'lishi uchun kichikroq qiymatlarni
  tavsiya qilaman).
