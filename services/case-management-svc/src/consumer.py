"""
Kafka Consumer and Event Ingestion processor for Case Management Service.
Listens to the 'case.created' topic published by upstream FWA Detection,
validates the event payload, enforces idempotency, initializes the 72-hour SLA clock,
and persists new audit case records into PostgreSQL.
"""

import argparse
import json
import logging
import signal
import sys
import threading
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Union
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.config import settings
from src.database import SessionLocal
from src.models import Case
from src.schemas import CaseCreate
from src import crud
from event_contracts import CaseCreatedEvent, CaseStatusEnum, SlaTypeEnum

logger = logging.getLogger("case-management.consumer")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class ConsumerError(Exception):
    """Custom exception raised when event processing or schema validation fails."""
    pass


def process_case_created_event(
    db: Session,
    raw_event: Union[dict, str, bytes, CaseCreatedEvent],
) -> Case:
    """
    Processes a 'case.created' event payload.
    Validates schema against CaseCreatedEvent contract, checks for idempotency,
    calculates the 72-hour human-confirmation SLA deadline, and creates the Case record.

    :param db: Active SQLAlchemy database session.
    :param raw_event: Raw Kafka message (bytes/str), dictionary, or validated CaseCreatedEvent.
    :return: Persisted or existing Case ORM model instance.
    :raises ConsumerError: If the payload cannot be parsed or fails schema validation.
    """
    # 1. Parse raw string/bytes into dictionary if needed
    if isinstance(raw_event, (str, bytes)):
        try:
            payload_dict = json.loads(raw_event)
        except Exception as e:
            logger.error(f"Failed to parse raw event JSON: {e}")
            raise ConsumerError(f"Malformed JSON payload: {e}") from e
    elif isinstance(raw_event, dict):
        payload_dict = raw_event
    elif isinstance(raw_event, CaseCreatedEvent):
        payload_dict = raw_event.model_dump(mode="json")
    else:
        raise ConsumerError(f"Unsupported event type: {type(raw_event)}")

    # 2. Validate against domain event contract
    try:
        if isinstance(raw_event, CaseCreatedEvent):
            event = raw_event
        else:
            event = CaseCreatedEvent.model_validate(payload_dict)
    except ValidationError as ve:
        logger.error(f"Event schema validation failed for 'case.created': {ve}")
        raise ConsumerError(f"Schema validation error: {ve}") from ve

    # 3. Idempotency Check: Prevent duplicate case rows on Kafka retries
    existing_case = crud.get_case_by_id(db, event.case_id)
    if existing_case:
        logger.warning(
            f"Case '{event.case_id}' already exists in database (status: {existing_case.status}). "
            f"Skipping duplicate insertion for claim '{event.claim_ref}'."
        )
        return existing_case

    # 4. Calculate 72-Hour SLA Confirmation Clock
    base_time = event.timestamp if event.timestamp else datetime.now(timezone.utc)
    sla_due_at = base_time + timedelta(hours=settings.DEFAULT_SLA_HOURS)

    # 5. Map to CaseCreate schema and persist
    case_create = CaseCreate(
        case_id=event.case_id,
        claim_ref=event.claim_ref,
        status=CaseStatusEnum.NEW,
        risk_score=event.risk_score,
        flagged_reason=event.flagged_reason,
        source_module=event.source_module,
        is_synthetic=event.is_synthetic,
        facility_npi=event.facility_npi,
        facility_name=event.facility_name,
        doctor_npi=event.doctor_npi,
        doctor_name=event.doctor_name,
        patient_id=event.patient_id,
        service_date=event.service_date,
        total_claim_amount=Decimal(str(event.total_claim_amount)),
        evidence_pointers=event.evidence_pointers,
        sla_due_at=sla_due_at,
        sla_type=SlaTypeEnum.INITIAL_REVIEW,
    )

    db_case = crud.create_case(db, case_create)
    logger.info(
        f"Successfully ingested case '{db_case.case_id}' for claim '{db_case.claim_ref}'. "
        f"Initial status: {db_case.status}, 72h SLA due at: {db_case.sla_due_at.isoformat()}."
    )
    return db_case


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def resolve_fixture_path(path_input: Union[str, Path]) -> Optional[Path]:
    """Resolves a file path either as an absolute path, relative to CWD, or relative to workspace root."""
    p = Path(path_input)
    if p.exists() and p.is_file():
        return p.resolve()
    candidate = WORKSPACE_ROOT / path_input
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()
    return None


def ingest_fixture_file(db: Session, fixture_path: Union[str, Path]) -> Case:
    """
    Reads a JSON fixture file from disk and ingests it into the database.
    Useful for unit testing, seed scripts, and local offline demo workflows.
    """
    resolved = resolve_fixture_path(fixture_path)
    if not resolved:
        raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

    with open(resolved, encoding="utf-8") as f:
        event_data = json.load(f)

    return process_case_created_event(db, event_data)


def publish_event_to_kafka(
    event_payload: Union[dict, str, Path],
    topic: Optional[str] = None,
    bootstrap_servers: Optional[str] = None,
) -> None:
    """
    Simulates upstream FWA Detection by publishing an event payload to Redpanda/Kafka.
    """
    from kafka import KafkaProducer

    target_topic = topic or settings.KAFKA_TOPIC_CASE_CREATED
    servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS

    # Load from file if path provided
    resolved_file = resolve_fixture_path(event_payload) if isinstance(event_payload, (str, Path)) else None
    if resolved_file:
        with open(resolved_file, encoding="utf-8") as f:
            data_str = f.read()
    elif isinstance(event_payload, dict):
        data_str = json.dumps(event_payload)
    else:
        data_str = str(event_payload)

    producer = KafkaProducer(
        bootstrap_servers=servers.split(","),
        value_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
    )

    future = producer.send(target_topic, value=data_str)
    record_metadata = future.get(timeout=10)
    producer.flush()
    logger.info(
        f"Published event to topic '{record_metadata.topic}' [{record_metadata.partition}] "
        f"at offset {record_metadata.offset} on '{servers}'."
    )


def start_consumer_loop(
    stop_event: Optional[threading.Event] = None,
    max_messages: Optional[int] = None,
) -> int:
    """
    Starts the live Kafka polling loop, consuming 'case.created' messages from Redpanda.
    """
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        settings.KAFKA_TOPIC_CASE_CREATED,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
        group_id=settings.KAFKA_CONSUMER_GROUP,
        auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
        enable_auto_commit=False,
        consumer_timeout_ms=1000,
    )

    logger.info(
        f"Kafka Consumer connected to '{settings.KAFKA_BOOTSTRAP_SERVERS}'. "
        f"Subscribed to topic '{settings.KAFKA_TOPIC_CASE_CREATED}' (group: '{settings.KAFKA_CONSUMER_GROUP}')."
    )

    processed_count = 0
    try:
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received, terminating consumer loop.")
                break

            # Poll for messages
            for message in consumer:
                if stop_event and stop_event.is_set():
                    break

                db = SessionLocal()
                try:
                    raw_payload = message.value.decode("utf-8") if isinstance(message.value, bytes) else message.value
                    process_case_created_event(db, raw_payload)
                    consumer.commit()
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing message offset {message.offset}: {e}")
                finally:
                    db.close()

                if max_messages and processed_count >= max_messages:
                    logger.info(f"Reached max_messages limit ({max_messages}). Exiting loop.")
                    return processed_count

    finally:
        logger.info("Closing Kafka consumer connection...")
        consumer.close()

    return processed_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WCT Module 5 Case Management Kafka Consumer")
    parser.add_argument("--fixture", "-f", type=str, help="Ingest a local mock fixture file directly into DB")
    parser.add_argument("--publish", "-p", type=str, help="Publish a local mock fixture file to Redpanda Kafka topic")
    args = parser.parse_args()

    if args.fixture:
        db_session = SessionLocal()
        try:
            case = ingest_fixture_file(db_session, args.fixture)
            print(f"Fixture ingested successfully! Case ID: {case.case_id}, Status: {case.status}")
        finally:
            db_session.close()
    elif args.publish:
        publish_event_to_kafka(args.publish)
        print(f"Fixture '{args.publish}' published to Kafka topic '{settings.KAFKA_TOPIC_CASE_CREATED}'.")
    else:
        # Graceful signal handler
        stop = threading.Event()

        def handle_signal(sig, frame):
            logger.info(f"Caught signal {sig}, shutting down...")
            stop.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        start_consumer_loop(stop_event=stop)
