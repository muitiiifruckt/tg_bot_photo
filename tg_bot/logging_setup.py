import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging() -> logging.Logger:
    """Configure base logging and return interaction logger."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    interaction_logger = logging.getLogger("user_interactions")
    interaction_logger.setLevel(logging.INFO)
    interaction_logger.propagate = False

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "user_interactions.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_formatter)

    # Avoid duplicate handlers if called multiple times
    if not any(isinstance(h, RotatingFileHandler) for h in interaction_logger.handlers):
        interaction_logger.addHandler(file_handler)

    return interaction_logger

