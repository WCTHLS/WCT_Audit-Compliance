"""
Temporal Worker process for WCT Module 5 Audit and Compliance Workflow.

Listens on the configured task queue, registers CaseAuditWorkflow and core activities,
and executes tasks dispatched by the Temporal server.
"""

import asyncio
import logging
import sys
from temporalio.client import Client
from temporalio.worker import Worker

from src.config import settings
from workflows.case_audit_workflow import CaseAuditWorkflow
from activities import (
    fetch_case_activity,
    summarize_case_activity,
    screen_exclusions_activity,
    notify_auditor_activity,
    send_follow_up_activity,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("workflow-worker")


async def run_worker() -> None:
    """Connects to Temporal and starts the worker loop."""
    logger.info(
        f"Connecting to Temporal cluster at '{settings.temporal_address}' "
        f"(namespace: '{settings.TEMPORAL_NAMESPACE}')..."
    )

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    logger.info(
        f"Connected successfully. Registering worker on task queue '{settings.TASK_QUEUE}'..."
    )

    worker = Worker(
        client,
        task_queue=settings.TASK_QUEUE,
        workflows=[CaseAuditWorkflow],
        activities=[
            fetch_case_activity,
            summarize_case_activity,
            screen_exclusions_activity,
            notify_auditor_activity,
            send_follow_up_activity,
        ],
    )

    logger.info(
        f"Worker is actively listening on task queue: '{settings.TASK_QUEUE}' "
        f"with {len(worker._activities)} registered activities."
    )
    await worker.run()


def main() -> None:
    """Entry point for the worker process."""
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped gracefully.")


if __name__ == "__main__":
    main()
