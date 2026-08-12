"""
Unit tests for the DLQ producer AND for process_document()'s
retry-exhaustion branch — the gap the reference docs (21, 24) never
actually closed (see docs/PHASE_4_IMPLEMENTATION_PLAN.md §6).

The retry-exhaustion test uses Celery's own `Task.apply(..., retries=N)`
to simulate "this is the Nth attempt" directly, rather than looping
through real retry mechanics (which behaves inconsistently under
task_always_eager across Celery versions) — much more reliable for a
unit test whose only job is to prove the DLQ-routing branch fires.
"""
import sys

import json
import pytest
from unittest.mock import AsyncMock, patch

class TestDLQProducer:
    @pytest.mark.asyncio
    async def test_publish_to_dlq_sends_expected_payload(self):
        from src.workers.dlq_producer import publish_to_dlq

        with patch("src.workers.dlq_producer.AIOKafkaProducer") as MockProducer:
            instance = MockProducer.return_value
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            instance.send_and_wait = AsyncMock()

            await publish_to_dlq(
                {"doc_id": "d-1", "job_id": "j-1", "tenant_id": "t-1", "r2_uri": "r2://b/k"},
                error="parser exploded",
            )

            instance.send_and_wait.assert_called_once()
            _, kwargs = instance.send_and_wait.call_args
            assert kwargs["topic"] == "doc-dlq"
            message = json.loads(kwargs["value"])
            assert message["doc_id"] == "d-1"
            assert message["error"] == "parser exploded"

    def test_publish_to_dlq_sync_wraps_the_async_version(self):
        from src.workers import dlq_producer
        with patch.object(dlq_producer, "publish_to_dlq", new=AsyncMock()) as mock_async:
            dlq_producer.publish_to_dlq_sync({"doc_id": "d-1"}, "boom")
        mock_async.assert_called_once()

class TestProcessDocumentRetryExhaustion:
    """Exercises process_document()'s terminal-failure branch directly —
    forces the parser to raise, and asserts the DLQ + mark_document_failed
    path fires instead of a fourth self.retry()."""

    def test_terminal_failure_routes_to_dlq_and_marks_document_failed(self):
        from src.workers.batch_worker import celery_app, process_document

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = False

        with patch(
            "src.workers.batch_worker.get_parser_for_uri",
            side_effect=RuntimeError("corrupt document"),
        ), patch(
            "src.workers.batch_worker.publish_to_dlq_sync"
        ) as mock_dlq, patch(
            "src.workers.batch_worker.mark_document_failed"
        ) as mock_mark_failed, patch(
            "src.workers.batch_worker.update_document_embedding_status"
        ):
            # retries=3 == max_retries=3 -> self.request.retries >=
            # self.max_retries is True on entry, so the task must take the
            # terminal-failure branch on THIS call, not retry again.
            process_document.apply(
                kwargs={
                    "doc_id": "d-1", "tenant_id": "t-1", "job_id": "j-1",
                    "r2_uri": "r2://bucket/corrupt.pdf",
                },
                retries=3,
            )

        mock_dlq.assert_called_once()
        payload, error = mock_dlq.call_args.kwargs["payload"], mock_dlq.call_args.kwargs["error"]
        assert payload["doc_id"] == "d-1"
        assert "corrupt document" in error
        mock_mark_failed.assert_called_once()

    def test_non_terminal_failure_retries_instead_of_publishing_to_dlq(self):
        from src.workers.batch_worker import celery_app, process_document
        from celery.exceptions import Retry

        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

        with patch(
            "src.workers.batch_worker.get_parser_for_uri",
            side_effect=RuntimeError("transient network blip"),
        ), patch("src.workers.batch_worker.publish_to_dlq_sync") as mock_dlq:
            # retries=0 -> 0 >= 3 is False -> must retry, not DLQ
            with pytest.raises(Retry):
                process_document.apply(
                    kwargs={
                        "doc_id": "d-1", "tenant_id": "t-1", "job_id": "j-1",
                        "r2_uri": "r2://bucket/flaky.pdf",
                    },
                    retries=0,
                    throw=True,
                )

        mock_dlq.assert_not_called()
