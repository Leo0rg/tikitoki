# Stage 1: Builder
# Используем официальный образ uv с предустановленным Python.
# См. https://docs.astral.sh/uv/guides/integration/docker/
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Для лучшего кеширования слоев сначала копируем только файлы, необходимые для установки зависимостей.
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости Python в виртуальное окружение.
# --no-install-project кеширует зависимости в отдельном слое от кода проекта.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Копируем остальной исходный код приложения.
COPY . .

# Устанавливаем сам проект в виртуальное окружение.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Устанавливаем Node.js и npm для обработки JavaScript-зависимостей.
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем JS-зависимости, игнорируя скрипты, чтобы избежать конфликтующих установок Playwright.
RUN npm install --prefix src/tiktokautouploader/Js_assets --ignore-scripts


# Stage 2: Финальный образ для запуска
FROM python:3.11-slim-bookworm AS final

# От имени root устанавливаем системные зависимости, необходимые для Playwright.
# Сначала копируем venv из builder, чтобы получить доступ к пакету playwright.
COPY --from=builder /app/.venv /tmp/.venv
RUN /tmp/.venv/bin/python -m playwright install-deps && rm -rf /tmp/.venv

# Также нам нужен Node.js для JS-частей загрузчика и curl для сетевых запросов.
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm curl && \
    rm -rf /var/lib/apt/lists/*

# Создаем непривилегированного пользователя для безопасности.
RUN useradd --create-home --shell /bin/bash appuser
USER appuser
WORKDIR /home/appuser

# Копируем код приложения, включая venv и node_modules, из builder.
# Владельцем будет `appuser`.
COPY --from=builder --chown=appuser:appuser /app/ .

# Устанавливаем PATH для использования виртуального окружения.
ENV PATH="/home/appuser/.venv/bin:$PATH"

# Устанавливаем браузеры Playwright от имени `appuser`. Они будут сохранены в `/home/appuser/.cache`.
RUN python -m playwright install

# Создаем директорию для логов.
RUN mkdir -p /home/appuser/logs

CMD ["python", "main.py"]
