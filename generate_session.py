"""
Bu skriptni FAQAT BIR MARTA, o'z shaxsiy kompyuteringizda ishga tushiring.
Maqsad: Telegram akkauntingiz uchun StringSession yaratish.
Bu session Render.com kabi serverda fayl (.session) o'rniga ishlatiladi.

Ishlatish:
    pip install telethon
    python generate_session.py

So'ralganda telefon raqamingiz va Telegram'dan kelgan kodni kiriting.
Oxirida chiqadigan uzun matnni SESSION_STRING nomli Environment Variable
sifatida Render.com'ga qo'shing. Bu matnni hech kimga bermang - u orqali
akkauntingizga to'liq kirish mumkin!
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("API_ID ni kiriting (my.telegram.org dan): "))
API_HASH = input("API_HASH ni kiriting: ")

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n--- SESSION_STRING (buni Render.com Environment Variable sifatida saqlang) ---\n")
    print(client.session.save())
    print("\n--- OGOHLANTIRISH: bu matnni hech kimga bermang! ---")
