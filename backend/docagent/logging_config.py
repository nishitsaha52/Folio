"""Consistent console logging without enabling verbose credential-bearing SDK logs."""

import logging

SDK_LOGGERS = (
    "httpx", "httpcore", "openai", "anthropic", "google.genai", "google.auth",
    "boto3", "botocore", "s3transfer", "urllib3", "sqlalchemy.engine",
)


def configure_logging(level: str):
    threshold = logging.getLevelNamesMapping()[level]
    logging.basicConfig(level=threshold, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().setLevel(threshold)
    logging.getLogger("docagent").setLevel(threshold)
    for name in SDK_LOGGERS:
        logging.getLogger(name).setLevel(max(threshold, logging.WARNING))
