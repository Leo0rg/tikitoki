import asyncio
from src.worker import run_worker
from src.loader import logger

if __name__ == "__main__":
    logger.info("Initializing worker application...")
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.exception(f"Unhandled exception in worker: {e}")
