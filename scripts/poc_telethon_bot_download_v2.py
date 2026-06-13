import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError


KNOWN_ERRORS = [
    "service is overloaded",
    "geoblock_required",
    "media not found or unavailable",
]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def ensure_login(client: TelegramClient) -> None:
    await client.connect()

    if await client.is_user_authorized():
        return

    phone = input("Enter your phone number with country code, for example +34600111222: ").strip()
    await client.send_code_request(phone)

    code = input("Enter the Telegram login code: ").strip()

    try:
        await client.sign_in(phone=phone, code=code)
    except SessionPasswordNeededError:
        password = input("Two-step verification enabled. Enter your Telegram password: ").strip()
        await client.sign_in(password=password)


def print_message(message) -> None:
    print("")
    print("========== BOT MESSAGE ==========")
    print(f"id: {message.id}")
    print(f"date: {message.date}")
    print(f"has_media: {bool(message.media)}")
    print("text:")
    print(message.raw_text or "<empty>")
    print("=================================")


async def main() -> None:
    load_dotenv()

    api_id = int(require_env("TELEGRAM_API_ID"))
    api_hash = require_env("TELEGRAM_API_HASH")
    session_name = os.getenv("TELETHON_SESSION_NAME", "telegram_user_session")

    bot_username = require_env("TELEGRAM_DOWNLOAD_BOT_USERNAME")
    instagram_url = require_env("POC_INSTAGRAM_URL")

    download_folder = Path(require_env("POC_DOWNLOAD_FOLDER"))
    download_folder.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(session_name, api_id, api_hash)
    await ensure_login(client)

    me = await client.get_me()
    print(f"Logged in as: {me.username or me.first_name} / id={me.id}")

    bot = await client.get_entity(bot_username)

    start_time = datetime.now(timezone.utc)
    downloaded_files: list[str] = []
    stop_event = asyncio.Event()

    @client.on(events.NewMessage(chats=bot))
    async def handler(event):
        message = event.message

        message_date = message.date
        if message_date and message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)

        # Ignorar mensajes antiguos.
        if message_date and message_date < start_time:
            return

        print_message(message)

        text = (message.raw_text or "").lower()

        if any(error in text for error in KNOWN_ERRORS):
            print("Known bot error detected:")
            print(message.raw_text)
            stop_event.set()
            return

        if message.media:
            print("Media detected. Downloading with Telethon...")
            downloaded_path = await client.download_media(
                message,
                file=str(download_folder)
            )

            if downloaded_path:
                downloaded_files.append(downloaded_path)
                print(f"Downloaded by Telethon: {downloaded_path}")
            else:
                print("Media was present, but Telethon did not return a file path.")

            # No paramos inmediatamente, porque un carrusel puede venir como varios mensajes.
            # Reiniciamos una espera corta fuera del handler.

    print("")
    print(f"Sending URL to bot {bot_username}:")
    print(instagram_url)

    sent = await client.send_message(bot, instagram_url)

    print("")
    print("========== SENT MESSAGE ==========")
    print(f"message_id: {sent.id}")
    print(f"date: {sent.date}")
    print(f"text: {sent.raw_text}")
    print("==================================")

    print("")
    print("Waiting for bot responses for up to 180 seconds...")

    total_timeout_seconds = 180
    no_new_file_grace_seconds = 20

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=total_timeout_seconds)
    except asyncio.TimeoutError:
        pass

    # Si descargó algo, damos una ventana extra para carruseles/múltiples ficheros.
    if downloaded_files:
        print("")
        print(f"Downloaded at least one file. Waiting {no_new_file_grace_seconds} seconds for more media...")
        await asyncio.sleep(no_new_file_grace_seconds)

    print("")
    print("POC finished.")
    print(f"Downloaded files: {len(downloaded_files)}")

    for file_path in downloaded_files:
        print(f"- {file_path}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())