from app.logging.task_logger import TaskLogger
from app.storage.sqlite import SQLiteStorage


def test_task_logger_redacts_secrets() -> None:
    storage = SQLiteStorage(":memory:")
    storage.init_db()
    logger = TaskLogger(storage)

    logger.log_event("t1", "llm_invoked", {"api_key": "secret", "nested": {"token": "abc"}})
    event = logger.get_logs("t1")[0]

    assert event.payload["api_key"] == "***"
    assert event.payload["nested"]["token"] == "***"
    assert "secret" not in str(event.payload)

