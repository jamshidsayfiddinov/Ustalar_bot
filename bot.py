"""
USTALRTOSHKENT Bot
-------------------
Vazifasi:
1. Qurilish/ustachilik mavzusidagi ochiq Telegram guruh va kanallarini avtomatik
   qidirib topadi va ularga sekin-asta (flood-limitga tushmaslik uchun) qo'shiladi.
2. Bot ishga tushganda, allaqachon a'zo bo'lgan barcha guruh/kanallardagi
   KECHA va BUGUN yozilgan xabarlarni BIR MARTA skanerlab chiqadi.
3. Shundan keyin YANGI kelayotgan xabarlarni ham real vaqtda kuzatib boradi.
4. Har bir xabarni Claude AI orqali tekshiradi: bu gipsokarton/kafel/elektrik/santexnika/
   bo'yoq va h.k. ustachilik ishimi yoki yo'qmi.
5. Agar mos kelsa:
   - Xabarda telefon raqami bo'lsa -> xabarni o'zgarishsiz kanalga forward qiladi.
   - Xabarda telefon raqami bo'lmasa -> xabar matni bilan BIRGA, yozgan odamning
     username yoki kontaktini ham qo'shib kanalga tashlaydi.

MUHIM ESLATMALAR:
- Bu shaxsiy Telegram akkauntingiz orqali ishlaydi (userbot), oddiy bot emas -
  shuning uchun juda ehtiyot bo'lish kerak: ko'p guruhga tez qo'shilish yoki
  ko'p xabar yuborish akkauntni bloklatib qo'yishi mumkin.
- Odamlarning shaxsiy ma'lumotini (username/kontakt/raqam) ularning roziligisiz
  ommaviy kanalga chiqarish O'zbekiston qonunchiligidagi shaxsiy ma'lumotlarni
  himoya qilish talablariga zid bo'lishi mumkin. Buni ehtiyotkorlik bilan, faqat
  ochiq guruhlarda ochiq e'lon qilingan ma'lumotlar uchun ishlatish tavsiya etiladi.
"""

import asyncio
import os
import re
import logging
from datetime import datetime, timedelta

from telethon import TelegramClient, events
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    ChannelsTooMuchError,
    ChatAdminRequiredError,
)
import requests

# ---------------------------------------------------------------------------
# SOZLAMALAR (barchasi Environment Variables orqali olinadi - kodga yozmang!)
# ---------------------------------------------------------------------------

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_STRING = os.environ.get("SESSION_STRING")  # StringSession uchun
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TARGET_CHANNEL = os.environ.get("TARGET_CHANNEL", "@USTALRTOSHKENT")

# Guruhlarni qidirish uchun kalit so'zlar
GROUP_SEARCH_KEYWORDS = [
    "usta toshkent",
    "qurilish toshkent",
    "remont toshkent",
    "santexnik toshkent",
    "elektrik toshkent",
    "gipsokarton",
    "kafelchi",
    "montaj xizmat",
]

# Ustachilik ishlarining kategoriyalari (AI ga ham, tez filtr uchun ham beriladi)
TRADE_KEYWORDS = [
    "gipsokarton", "kafel", "elektrik", "santexnik", "bo'yoq", "shpaklyovka",
    "montaj", "remont", "quruvchi", "usta", "plitka", "laminat", "eshik",
    "deraza", "potolok", "linoleum", "obои", "плитка", "гипсокартон",
    "электрик", "сантехник", "ремонт",
]

PHONE_REGEX = re.compile(r"(\+?998[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})|(\b\d{9}\b)")

# Guruhga qo'shilish orasidagi kutish vaqti (soniya) - flood-limitdan qochish uchun
JOIN_DELAY_SECONDS = 45
MAX_GROUPS_PER_RUN = 8

# Tarixiy skanerlashda nechta kunlik xabarlarni o'qish kerak (0 = faqat bugun, 1 = kecha+bugun)
HISTORY_SCAN_DAYS_BACK = 1
# Xavfsizlik uchun har bir chatda tekshiriladigan maksimal xabarlar soni
# (juda faol guruhda cheksiz aylanib qolmaslik uchun)
MAX_MESSAGES_SAFETY_CAP = 500
# Tarixiy xabarlarni tekshirish orasida biroz kutish (faqat AI chaqiriladigan xabarlar uchun)
HISTORY_SCAN_DELAY_SECONDS = 0.3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ustalar_bot")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

if SESSION_STRING:
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    client = TelegramClient("ustalar_session", API_ID, API_HASH)

# Bot ishga tushgan vaqt - shundan oldingi xabarlarni umuman ko'rib chiqmaymiz
BOT_START_TIME = None
# Qo'shilgan guruhlar ro'yxati (runtime uchun; xohlasangiz storage.py bilan saqlash mumkin)
JOINED_GROUP_IDS = set()

# Postlangan xabarlarni takrorlamaslik uchun fayl - (chat_id, message_id) juftliklarini saqlaydi
POSTED_IDS_FILE = "posted_ids.txt"
POSTED_IDS = set()


def load_posted_ids():
    """Diskdan avval postlangan xabarlar ro'yxatini yuklaydi (qayta ishga tushirilganda takrorlamaslik uchun)."""
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    POSTED_IDS.add(line)
    log.info("Yuklandi: %d ta avval postlangan xabar ID.", len(POSTED_IDS))


def mark_as_posted(chat_id: int, message_id: int):
    """Xabarni postlangan deb belgilaydi va diskka yozadi."""
    key = f"{chat_id}:{message_id}"
    POSTED_IDS.add(key)
    with open(POSTED_IDS_FILE, "a") as f:
        f.write(key + "\n")


def already_posted(chat_id: int, message_id: int) -> bool:
    return f"{chat_id}:{message_id}" in POSTED_IDS


# ---------------------------------------------------------------------------
# 1-QISM: GURUHLARNI QIDIRISH VA QO'SHILISH
# ---------------------------------------------------------------------------

async def discover_and_join_groups():
    """Kalit so'zlar bo'yicha ochiq guruhlarni qidiradi va sekin-asta qo'shiladi."""
    joined_count = 0

    for keyword in GROUP_SEARCH_KEYWORDS:
        if joined_count >= MAX_GROUPS_PER_RUN:
            log.info("Bir martalik qo'shilish limiti (%d) tugadi, keyingi ishga tushishda davom etadi.", MAX_GROUPS_PER_RUN)
            break

        try:
            result = await client(SearchRequest(q=keyword, limit=10))
        except FloodWaitError as e:
            log.warning("Qidiruvda flood-wait: %s soniya kutamiz", e.seconds)
            await asyncio.sleep(e.seconds)
            continue
        except Exception as e:
            log.error("Qidirishda xatolik (%s): %s", keyword, e)
            continue

        for chat in result.chats:
            if joined_count >= MAX_GROUPS_PER_RUN:
                break
            if chat.id in JOINED_GROUP_IDS:
                continue
            # Faqat ochiq (megagroup/broadcast bo'lmagan yoki umuman public) guruhlarga qo'shilamiz
            username = getattr(chat, "username", None)
            if not username:
                continue  # Faqat public username'i bor guruhlarga xavfsiz qo'shiladi

            try:
                await client(JoinChannelRequest(username))
                JOINED_GROUP_IDS.add(chat.id)
                joined_count += 1
                log.info("Qo'shildik: @%s (%s)", username, chat.title)
                await asyncio.sleep(JOIN_DELAY_SECONDS)
            except UserAlreadyParticipantError:
                JOINED_GROUP_IDS.add(chat.id)
            except FloodWaitError as e:
                log.warning("Qo'shilishda flood-wait: %s soniya kutamiz", e.seconds)
                await asyncio.sleep(e.seconds)
            except ChannelsTooMuchError:
                log.error("Juda ko'p kanal/guruhga a'zosiz - limitga yetdi. To'xtatildi.")
                return
            except Exception as e:
                log.error("'@%s' ga qo'shilishda xatolik: %s", username, e)


# ---------------------------------------------------------------------------
# 2-QISM: XABARNI TAHLIL QILISH (AI orqali)
# ---------------------------------------------------------------------------

def quick_keyword_check(text: str) -> bool:
    """Tez, arzon dastlabki filtr - AI chaqirishdan oldin aniq mos kelmaydiganlarni chiqarib tashlaydi."""
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in TRADE_KEYWORDS)


async def is_construction_job_post(text: str) -> bool:
    """Claude AI orqali (requests/HTTP orqali) xabar chindan ham ustachilik ishi/e'loni ekanini tekshiradi."""
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 10,
        "messages": [{
            "role": "user",
            "content": (
                "Quyidagi Telegram xabari qurilish/ustachilik xizmati bilan bog'liqmi "
                "(masalan: gipsokarton, kafel, elektrik, santexnika, bo'yoq, remont, "
                "montaj kabi ish/e'lon/vakansiya)? Faqat 'HA' yoki 'YOQ' deb javob ber.\n\n"
                f"Xabar: {text}"
            )
        }]
    }
    try:
        # requests kutubxonasi sinxron - alohida thread'da ishga tushiramiz
        # asyncio event loop'ni bloklamaslik uchun
        response = await asyncio.to_thread(
            requests.post, ANTHROPIC_API_URL, headers=ANTHROPIC_HEADERS, json=payload, timeout=30
        )
        if response.status_code >= 400:
            log.error("Claude API xatoligi (%d): %s", response.status_code, response.text[:300])
            return False
        data = response.json()
        answer = data["content"][0]["text"].strip().upper()
        return answer.startswith("HA")
    except Exception as e:
        log.error("Claude API xatoligi: %s", e)
        return False


def extract_phone(text: str) -> str | None:
    match = PHONE_REGEX.search(text or "")
    return match.group(0) if match else None


async def process_message_text(text: str, get_sender_coro, chat_id: int, message_id: int) -> bool:
    """
    Umumiy tahlil mantiqi - ham tarixiy, ham yangi xabarlar uchun ishlatiladi.
    get_sender_coro - yuboruvchini olish uchun chaqiriladigan async funksiya (kerak bo'lgandagina).
    Xabar joylangan bo'lsa True qaytaradi.
    """
    if already_posted(chat_id, message_id):
        return False

    if not quick_keyword_check(text):
        return False

    if not await is_construction_job_post(text):
        return False

    phone = extract_phone(text)
    sender = await get_sender_coro()
    sender_username = getattr(sender, "username", None) if sender else None

    await post_to_channel(
        message_text=text,
        sender_username=sender_username,
        sender_phone_contact=None,
        has_phone=bool(phone),
    )
    mark_as_posted(chat_id, message_id)
    return True


# ---------------------------------------------------------------------------
# 3-QISM: KANALGA JOYLASH
# ---------------------------------------------------------------------------

async def post_to_channel(message_text: str, sender_username: str | None, sender_phone_contact: str | None, has_phone: bool):
    """Filtrlangan xabarni kanalga joylaydi."""
    if has_phone:
        # Xabarda raqam bor - o'zgarishsiz forward qilamiz
        final_text = message_text
    else:
        # Raqam yo'q - yozgan odamning username/kontaktini biriktirib qo'shamiz
        contact_line = ""
        if sender_username:
            contact_line = f"\n\n👤 E'lon egasi: @{sender_username}"
        elif sender_phone_contact:
            contact_line = f"\n\n👤 E'lon egasi kontakti: {sender_phone_contact}"
        else:
            contact_line = "\n\n👤 E'lon egasi: (kontakt topilmadi)"
        final_text = f"{message_text}{contact_line}"

    try:
        await client.send_message(TARGET_CHANNEL, final_text)
        log.info("Kanalga joylandi.")
    except Exception as e:
        log.error("Kanalga joylashda xatolik: %s", e)


# ---------------------------------------------------------------------------
# 4-QISM: MAVJUD GURUH/KANALLARDAGI O'QILMAGAN XABARLARNI BIR MARTALIK SKANERLASH
# ---------------------------------------------------------------------------

async def scan_recent_messages():
    """
    Bot ishga tushganda, a'zo bo'lgan barcha guruh va kanallardagi KECHA va BUGUN
    yozilgan xabarlarni (o'qilgan/o'qilmaganidan qat'iy nazar) bir marta tekshirib chiqadi.
    """
    log.info("Kecha va bugungi xabarlarni skanerlash boshlandi...")
    total_checked = 0
    total_posted = 0

    # Telefon/serverning mahalliy vaqt zonasi bo'yicha "bugun"ni aniqlaymiz
    now_local = datetime.now().astimezone()
    cutoff_date = (now_local - timedelta(days=HISTORY_SCAN_DAYS_BACK)).date()

    async for dialog in client.iter_dialogs():
        # Faqat guruh va kanallarni tekshiramiz (shaxsiy chatlarni emas)
        if not (dialog.is_group or dialog.is_channel):
            continue

        scanned_in_chat = 0
        try:
            async for message in client.iter_messages(dialog.entity, limit=MAX_MESSAGES_SAFETY_CAP):
                # Xabarlar odatda yangidan eskiga qarab keladi - sana chegarasidan
                # o'tib ketsak, shu chat uchun to'xtatamiz
                message_local_date = message.date.astimezone().date()
                if message_local_date < cutoff_date:
                    break

                scanned_in_chat += 1
                if not message.message:
                    continue

                total_checked += 1

                # Tez kalit-so'z filtridan o'tmagan xabarlar uchun kutish shart emas -
                # faqat AI ga yuboriladigan (kalit so'zga mos) xabarlar uchun ozgina kutamiz
                if not quick_keyword_check(message.message):
                    continue

                async def get_sender(msg=message):
                    try:
                        return await msg.get_sender()
                    except Exception:
                        return None

                posted = await process_message_text(
                    message.message, get_sender, dialog.entity.id, message.id
                )
                if posted:
                    total_posted += 1

                await asyncio.sleep(HISTORY_SCAN_DELAY_SECONDS)

            if scanned_in_chat >= MAX_MESSAGES_SAFETY_CAP:
                log.warning(
                    "'%s' juda faol - xavfsizlik chegarasi (%d) ga yetdi, "
                    "ba'zi eski xabarlar tekshirilmagan bo'lishi mumkin.",
                    dialog.name, MAX_MESSAGES_SAFETY_CAP,
                )

        except FloodWaitError as e:
            log.warning("Tarixiy skanerlashda flood-wait: %s soniya kutamiz", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.error("'%s' dagi tarixni skanerlashda xatolik: %s", dialog.name, e)

    log.info(
        "Kecha/bugungi xabarlarni skanerlash tugadi. Tekshirildi: %d, kanalga joylandi: %d",
        total_checked, total_posted,
    )


# ---------------------------------------------------------------------------
# 5-QISM: YANGI XABARLARNI TINGLASH (guruh va kanallar, real vaqtda)
# ---------------------------------------------------------------------------

@client.on(events.NewMessage(chats=None))
async def handle_new_message(event):
    # Guruh va kanal xabarlarini ko'rib chiqamiz (shaxsiy xabarlarni emas)
    if not (event.is_group or event.is_channel):
        return

    text = event.message.message or ""

    async def get_sender():
        try:
            return await event.get_sender()
        except Exception:
            return None

    await process_message_text(text, get_sender, event.chat_id, event.message.id)


# ---------------------------------------------------------------------------
# ISHGA TUSHIRISH
# ---------------------------------------------------------------------------

async def main():
    global BOT_START_TIME
    load_posted_ids()
    await client.start()
    BOT_START_TIME = datetime.now().timestamp()
    log.info("Bot ishga tushdi.")

    # Avval kecha va bugungi xabarlarni bir marta skanerlaymiz
    await scan_recent_messages()

    # Guruhlarni qidirib, qo'shilishni fon vazifasi sifatida ishga tushiramiz
    asyncio.create_task(discover_and_join_groups())

    log.info("Yangi xabarlarni tinglash boshlandi...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
       
