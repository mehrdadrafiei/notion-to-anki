import json
import logging
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }

        if hasattr(record, "error_code"):
            log_data["error_code"] = record.error_code

        if hasattr(record, "details"):
            log_data["details"] = record.details

        return json.dumps(log_data)


def setup_logging() -> None:
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
