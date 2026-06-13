import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def print_message(prefix: str, message) -> None:
    text = message.raw_text or ""
    has_media = bool(message.media)

    print("")
    print(f"========== {prefix} ==========")
    print(f"message_id: {message.id}")
    print(f"date: {message.date}")
    print(f"has_media: {has_media}")
    print("text:")
    print(text if text else "<empty>")
    print("==============================")
    print("")


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

    print("Connecting to Telegram...")

    await client.connect()

    if not await client.is_user_authorized():
        print("No active Telegram session found.")
        phone = input("Enter your phone number with country code, for example +34600111222: ").strip()

        await client.send_code_request(phone)
        code = input("Enter the Telegram login code: ").strip()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = input("Two-step verification enabled. Enter your Telegram password: ").strip()
            await client.sign_in(password=password)

    me = await client.get_me()
    print(f"Logged in as: {me.username or me.first_name} / id={me.id}")

    bot = await client.get_entity(bot_username)

    before_send_utc = datetime.now(timezone.utc)

    print("")
    print(f"Sending URL to bot {bot_username}:")
    print(instagram_url)

    sent_message = await client.send_message(bot, instagram_url)
    print_message("SENT MESSAGE", sent_message)

    print(f"Waiting for bot responses for up to 180 seconds...")
    print("The script will print text responses and download media responses.")

    downloaded_files: list[str] = []
    received_messages = 0

    async with client.conversation(bot, timeout=180) as conversation:
        # Importante:
        # Como el mensaje ya se envió con client.send_message(), aquí solo esperamos respuestas.
        # Algunos bots responden con varios mensajes: texto, foto, vídeo, documento, etc.
        while True:
            try:
                response = await conversation.get_response()
            except asyncio.TimeoutError:
                print("Timeout reached. No more bot responses.")
                break

            # Evitar mensajes antiguos por seguridad.
            if response.date and response.date.replace(tzinfo=timezone.utc) < before_send_utc:
                continue

            received_messages += 1
            print_message("BOT RESPONSE", response)

            response_text = (response.raw_text or "").lower()

            known_errors = [
                "service is overloaded",
                "geoblock_required",
                "media not found or unavailable",
            ]

            if any(error in response_text for error in known_errors):
                print("Known bot error detected:")
                print(response.raw_text)
                # Para la POC no reintentamos; solo mostramos el error.
                break

            if response.media:
                print("Media detected. Downloading...")
                downloaded_path = await client.download_media(
                    response,
                    file=str(download_folder)
                )

                if downloaded_path:
                    downloaded_files.append(downloaded_path)
                    print(f"Downloaded: {downloaded_path}")
                else:
                    print("Telethon did not return a downloaded path.")

            # Criterio simple de salida para POC:
            # si ya descargó al menos un archivo, esperamos un poco más por si viene carrusel.
            # Si el bot tarda mucho entre archivos, puede que necesites aumentar este valor.
            if downloaded_files:
                try:
                    extra_response = await asyncio.wait_for(
                        conversation.get_response(),
                        timeout=15
                    )

                    received_messages += 1
                    print_message("BOT EXTRA RESPONSE", extra_response)

                    if extra_response.media:
                        downloaded_path = await client.download_media(
                            extra_response,
                            file=str(download_folder)
                        )
                        if downloaded_path:
                            downloaded_files.append(downloaded_path)
                            print(f"Downloaded: {downloaded_path}")

                    # Continuamos por si hay más mensajes.
                    continue

                except asyncio.TimeoutError:
                    print("No extra media received after 15 seconds. Finishing POC.")
                    break

    print("")
    print("POC finished.")
    print(f"Bot messages received: {received_messages}")
    print(f"Downloaded files: {len(downloaded_files)}")

    for file_path in downloaded_files:
        print(f"- {file_path}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())