import asyncio
import json
import os
import tempfile
from typing import List, Literal, Optional

import boto3
from faststream.rabbit import RabbitBroker
from loguru import logger
from pydantic import BaseModel, Field
from src.loader import config
from src.tiktokautouploader.function import login_only, upload_tiktok


class TikTokUploadMessage(BaseModel):
    s3_video_key: str = Field(..., description="Ключ (путь) к видеофайлу в S3 бакете.")
    account_name: str = Field(..., description="Имя аккаунта для загрузки видео.")
    tiktok_username: Optional[str] = Field(
        default=None, description="Имя пользователя TikTok для входа."
    )
    tiktok_password: Optional[str] = Field(
        default=None, description="Пароль от аккаунта TikTok для входа."
    )
    description: str = Field(..., description="Описание для видео.")
    hashtags: Optional[List[str]] = Field(default=None, description="Список хэштегов.")
    sound_name: Optional[str] = Field(
        default=None, description="Название звука для использования."
    )
    proxy: Optional[dict] = Field(
        default=None,
        description="Словарь с данными для прокси: {'host', 'port', 'user', 'pass'}",
    )
    favorite_sound_name: Optional[str] = Field(
        default=None, description="Название любимого звука для использования."
    )
    sound_aud_vol: Optional[Literal["main", "mix", "background"]] = Field(
        default=None,
        description="Громкость звука для использования: 'main', 'mix' или 'background'.",
    )
    # headless: bool = Field(default=True, description="Run browser in headless mode.")
    # stealth: bool = Field(default=True, description="Use stealth mode to mimic human behavior.")


class TikTokCookieMessage(BaseModel):
    account_name: str = Field(
        ..., description="Имя аккаунта TikTok для сохранения cookie."
    )
    cookies_json: str = Field(..., description="Строка JSON с cookie.")
    tg_user_id: int = Field(
        ..., description="ID пользователя в Telegram для обратной связи."
    )


class TikTokLoginMessage(BaseModel):
    tg_user_id: int
    account_name: str
    tiktok_username: str
    tiktok_password: str
    proxy: Optional[dict] = None


class LoginStatusMessage(BaseModel):
    tg_user_id: int
    success: bool
    message: str


class CookieStatusMessage(BaseModel):
    tg_user_id: int
    account_name: str
    success: bool
    message: str


broker = RabbitBroker(config.rabbitmq.url)

s3_client = boto3.client(
    "s3",
    endpoint_url=config.s3.endpoint_url,
    aws_access_key_id=config.s3.access_key_id,
    aws_secret_access_key=config.s3.secret_access_key,
)


def format_proxy(proxy_data: Optional[dict]) -> Optional[dict]:
    """Formats the proxy data to the format expected by the upload_tiktok function."""
    if not proxy_data:
        return None

    logger.debug(f"Proxy data: {proxy_data}")

    # Construct the server string from host and port, ensuring the protocol is present
    host = proxy_data.get("host")
    port = proxy_data.get("port")
    server = f"http://{host}:{port}"

    formatted = {"server": server}

    # Only add username and password if they are present
    if proxy_data.get("username"):
        formatted["username"] = proxy_data["username"]
    if proxy_data.get("password"):
        formatted["password"] = proxy_data["password"]

    return formatted


@broker.subscriber("login_tasks")
async def handle_tiktok_login(msg: TikTokLoginMessage):
    """
    Handles a message to log in to TikTok and save cookies.
    """
    logger.info(
        f"Received login task for account: {msg.account_name} with password {msg.tiktok_password}"
    )

    formatted_proxy = format_proxy(msg.proxy)

    try:
        success, message = await asyncio.to_thread(
            login_only,
            accountname=msg.account_name,
            tiktok_username=msg.tiktok_username,
            tiktok_password=msg.tiktok_password,
            proxy=formatted_proxy,
            headless=False,
        )

        status_message = LoginStatusMessage(
            tg_user_id=msg.tg_user_id, success=success, message=message
        )

    except Exception as e:
        logger.exception(f"An error occurred during login for {msg.account_name}: {e}")
        status_message = LoginStatusMessage(
            tg_user_id=msg.tg_user_id,
            success=False,
            message=f"Внутренняя ошибка воркера: {e}",
        )

    await broker.publish(status_message, queue="login_status")
    logger.info(f"Sent login status for account {msg.account_name} back to the bot.")


@broker.subscriber("cookies_tasks")
async def handle_tiktok_cookies(msg: TikTokCookieMessage):
    """
    Handles a message to update TikTok cookies from a JSON string.
    Normalizes cookie format from different sources.
    """
    logger.info(f"Received cookie update task for account: {msg.account_name}")
    try:
        cookies_data = json.loads(msg.cookies_json)

        normalized_cookies = []
        for cookie in cookies_data:
            if not all(k in cookie for k in ["name", "value", "domain", "path"]):
                logger.warning(f"Skipping malformed cookie: {cookie}")
                continue

            new_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie["path"],
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
            }

            if "expirationDate" in cookie and cookie["expirationDate"] is not None:
                new_cookie["expires"] = int(cookie["expirationDate"])
            elif cookie.get("session", False):
                new_cookie["expires"] = -1
            elif "expires" not in cookie:
                new_cookie["expires"] = -1

            same_site = cookie.get("sameSite")
            if same_site is None or same_site == "no_restriction":
                new_cookie["sameSite"] = "None"
            elif same_site in ["Lax", "Strict", "None"]:
                new_cookie["sameSite"] = same_site
            else:
                new_cookie["sameSite"] = "Lax"

            normalized_cookies.append(new_cookie)

        if not normalized_cookies:
            raise ValueError("No valid cookies were found after normalization.")

        file_path = f"TK_cookies_{msg.account_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(normalized_cookies, f, indent=4, ensure_ascii=False)

        logger.success(
            f"Successfully saved and normalized cookies for account: {msg.account_name}"
        )

        status_message = CookieStatusMessage(
            tg_user_id=msg.tg_user_id,
            account_name=msg.account_name,
            success=True,
            message=f"Куки для аккаунта '{msg.account_name}' успешно обновлены.",
        )

    except json.JSONDecodeError:
        logger.error(
            f"Failed to parse cookies JSON string for account {msg.account_name}."
        )
        status_message = CookieStatusMessage(
            tg_user_id=msg.tg_user_id,
            account_name=msg.account_name,
            success=False,
            message="Ошибка: не удалось обработать данные куков. Убедитесь, что они в формате JSON.",
        )
    except Exception as e:
        logger.exception(
            f"An error occurred while processing cookies for {msg.account_name}: {e}"
        )
        status_message = CookieStatusMessage(
            tg_user_id=msg.tg_user_id,
            account_name=msg.account_name,
            success=False,
            message=f"Произошла внутренняя ошибка при обработке куков для аккаунта '{msg.account_name}'.",
        )

    await broker.publish(status_message, queue="cookie_status")
    logger.info(
        f"Sent cookie processing status for account {msg.account_name} back to the bot."
    )


@broker.subscriber("video_tasks")
async def handle_tiktok_upload(msg: TikTokUploadMessage):
    """
    Handles a message to upload a TikTok video.
    It downloads the video from S3, uploads it to TikTok, and then cleans up.
    """
    logger.debug("Start polling for new task")
    logger.info(
        f"Received new task for account: {msg.account_name}, s3_key: {msg.s3_video_key}"
    )

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        local_video_path = temp_video.name
        logger.info(f"Created temporary file for video: {local_video_path}")

        try:
            logger.info(f"Downloading video from S3: {msg.s3_video_key}")
            await asyncio.to_thread(
                s3_client.download_file,
                config.s3.bucket_name,
                msg.s3_video_key,
                local_video_path,
            )
            logger.info(f"Video downloaded successfully to {local_video_path}")

            logger.info("Starting TikTok upload process...")

            # Format the proxy data before passing it to the uploader
            formatted_proxy = format_proxy(msg.proxy)

            logger.debug(f"Formatted proxy: {formatted_proxy}")

            await asyncio.to_thread(
                upload_tiktok,
                video=local_video_path,
                description=msg.description,
                accountname=msg.account_name,
                tiktok_username=msg.tiktok_username,
                tiktok_password=msg.tiktok_password,
                hashtags=msg.hashtags,
                sound_name=msg.sound_name,
                favorite_sound_name=msg.favorite_sound_name,
                sound_aud_vol=msg.sound_aud_vol,
                proxy=formatted_proxy,
                headless=True,
                stealth=True,
                suppressprint=True,
            )
            logger.success(
                f"Successfully uploaded video for account: {msg.account_name}"
            )

        except Exception as e:
            logger.exception(
                f"An error occurred while processing task for {msg.account_name}: {e}"
            )
        finally:
            if os.path.exists(local_video_path):
                os.remove(local_video_path)
                logger.info(f"Cleaned up temporary file: {local_video_path}")


async def run_worker():
    logger.info("Starting worker...")
    await broker.start()
    await asyncio.Future()
