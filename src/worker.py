import asyncio
import os
import boto3
import tempfile
from loguru import logger
from pydantic import BaseModel, Field
from typing import Optional, List

from faststream.rabbit import RabbitBroker

from src.loader import config
from src.tiktokautouploader.function import upload_tiktok, login_with_qr_and_save_cookies


class TikTokUploadMessage(BaseModel):
    tg_user_id: int = Field(..., description="ID пользователя в Telegram для обратной связи.")
    s3_video_key: str = Field(..., description="Ключ (путь) к видеофайлу в S3 бакете.")
    account_name: str = Field(..., description="Имя аккаунта для загрузки видео.")
    description: str = Field(..., description="Описание для видео.")
    hashtags: Optional[List[str]] = Field(default=None, description="Список хэштегов.")
    sound_name: Optional[str] = Field(default=None, description="Название звука для использования.")
    proxy: Optional[dict] = Field(default=None, description="Словарь с данными для прокси: {'host', 'port', 'user', 'pass'}")
    # headless: bool = Field(default=True, description="Run browser in headless mode.")
    # stealth: bool = Field(default=True, description="Use stealth mode to mimic human behavior.")


class TikTokLoginMessage(BaseModel):
    tg_user_id: int = Field(..., description="ID пользователя в Telegram.")
    account_name: str = Field(..., description="Имя аккаунта TikTok для входа.")
    proxy: Optional[dict] = Field(default=None, description="Данные прокси.")


class QRCodeMessage(BaseModel):
    tg_user_id: int = Field(..., description="ID пользователя в Telegram для отправки QR-кода.")
    qr_code_data: str = Field(..., description="Данные QR-кода (например, base64-строка или URL).")


class LoginStatusMessage(BaseModel):
    tg_user_id: int = Field(..., description="ID пользователя в Telegram.")
    success: bool = Field(..., description="Статус входа: True, если успешно.")
    message: str = Field(..., description="Сообщение для пользователя.")


broker = RabbitBroker(config.rabbitmq.url)

s3_client = boto3.client(
    's3',
    endpoint_url=config.s3.endpoint_url,
    aws_access_key_id=config.s3.access_key_id,
    aws_secret_access_key=config.s3.secret_access_key
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


@broker.subscriber("video_tasks")
async def handle_tiktok_upload(msg: TikTokUploadMessage):
    """
    Handles a message to upload a TikTok video.
    It downloads the video from S3, uploads it to TikTok, and then cleans up.
    """
    logger.debug("Start polling for new task")
    logger.info(f"Received new task for account: {msg.account_name}, s3_key: {msg.s3_video_key}")

    async def send_qr_code(qr_data: str):
        """Callback to send QR code data to RabbitMQ."""
        logger.info(f"Sending QR code to user {msg.tg_user_id}")
        qr_message = QRCodeMessage(tg_user_id=msg.tg_user_id, qr_code_data=qr_data)
        await broker.publish(qr_message, queue="qr_codes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
        local_video_path = temp_video.name
        logger.info(f"Created temporary file for video: {local_video_path}")

        try:
            logger.info(f"Downloading video from S3: {msg.s3_video_key}")
            await asyncio.to_thread(
                s3_client.download_file,
                config.s3.bucket_name,
                msg.s3_video_key,
                local_video_path
            )
            logger.info(f"Video downloaded successfully to {local_video_path}")

            logger.info("Starting TikTok upload process...")
            
            # Format the proxy data before passing it to the uploader
            formatted_proxy = format_proxy(msg.proxy)
            
            logger.debug(f"Formatted proxy: {formatted_proxy}")
            
            await upload_tiktok(
                video=local_video_path,
                description=msg.description,
                accountname=msg.account_name,
                qr_callback=send_qr_code,
                hashtags=msg.hashtags,
                sound_name=msg.sound_name,
                proxy=formatted_proxy,
                headless=False,
                stealth=True,
            )
            logger.success(f"Successfully uploaded video for account: {msg.account_name}")

        except Exception as e:
            logger.exception(f"An error occurred while processing task for {msg.account_name}: {e}")
        finally:
            if os.path.exists(local_video_path):
                os.remove(local_video_path)
                logger.info(f"Cleaned up temporary file: {local_video_path}")


async def run_worker():
    logger.info("Starting worker...")
    await broker.start()
    await asyncio.Future() 


@broker.subscriber("login_tasks")
async def handle_tiktok_login(msg: TikTokLoginMessage):
    """Handles a message to initiate TikTok login via QR code."""
    logger.info(f"Received login task for account: {msg.account_name}")

    async def send_qr_code(qr_data: str):
        logger.info(f"Sending QR code to user {msg.tg_user_id}")
        qr_message = QRCodeMessage(tg_user_id=msg.tg_user_id, qr_code_data=qr_data)
        await broker.publish(qr_message, queue="qr_codes_login")

    try:
        formatted_proxy = format_proxy(msg.proxy)
        login_success, message = await login_with_qr_and_save_cookies(
            accountname=msg.account_name,
            proxy=formatted_proxy,
            qr_callback=send_qr_code
        )
        status_message = LoginStatusMessage(
            tg_user_id=msg.tg_user_id,
            success=login_success,
            message=message
        )
        await broker.publish(status_message, queue="login_status")

        if login_success:
            logger.success(f"Successfully logged in for account: {msg.account_name}")
        else:
            logger.error(f"Failed to log in for account: {msg.account_name}: {message}")

    except Exception as e:
        logger.exception(f"An error occurred during login for {msg.account_name}: {e}")
        error_status = LoginStatusMessage(
            tg_user_id=msg.tg_user_id,
            success=False,
            message=f"Произошла критическая ошибка в воркере: {e}"
        )
        await broker.publish(error_status, queue="login_status") 