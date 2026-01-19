import logging

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure application logging."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger("HuggBackend")

logger = setup_logging()
