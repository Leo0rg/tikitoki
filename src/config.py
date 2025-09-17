from typing import Optional


class Validate:
    def validate_fields(self):
        for field, value in self.__dict__.items():
            if value is None:
                raise ValueError(
                    f"Field '{field}' is None. All fields must be initialized."
                )


class S3Config(Validate):
    def __init__(
        self,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket_name = bucket_name
        self.validate_fields()


class RabbitMQConfig(Validate):
    def __init__(self, user: str, password: str, host: str, port: int):
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.validate_fields()

    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/"


class Config:
    def __init__(self):
        self.s3: Optional[S3Config] = None
        self.rabbitmq: Optional[RabbitMQConfig] = None

    def configure_s3(
        self,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ):
        self.s3 = S3Config(endpoint_url, access_key_id, secret_access_key, bucket_name)

    def configure_rabbitmq(self, user: str, password: str, host: str, port: int):
        self.rabbitmq = RabbitMQConfig(user, password, host, port)
