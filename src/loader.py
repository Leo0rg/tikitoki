import os

from dotenv import load_dotenv
from loguru import logger

from src.config import Config

# Загружаем переменные окружения из .env файла
load_dotenv()

# Создаем экземпляр конфигурации
config = Config()

config.configure_s3(
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
    secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
    bucket_name=os.getenv("S3_BUCKET_NAME"),
)

config.configure_rabbitmq(
    user=os.getenv("RABBITMQ_USER"),
    password=os.getenv("RABBITMQ_PASS"),
    host=os.getenv("RABBITMQ_HOST"),
    port=int(os.getenv("RABBITMQ_PORT")),
)

logger.add("logs/worker.log", rotation="500 MB")
logger.info("Configuration loaded.")
logger.info(f"RabbitMQ URL: {config.rabbitmq.url}")
logger.info(f"S3 Endpoint: {config.s3.endpoint_url}")
logger.debug(f"S3 Bucket: {config.s3.bucket_name}")
