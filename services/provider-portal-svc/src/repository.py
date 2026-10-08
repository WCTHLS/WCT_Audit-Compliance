"""
Repository layer for Provider Portal Service.
Provides thread-safe in-memory storage for document requests, read receipts, and responses.
"""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import threading
from typing import Dict, List, Optional
import uuid

from src.config import settings
from src.schemas import (
    DocumentFileAttachment,
    DocumentRequestCreate,
    DocumentRequestResponse,
    DocumentResponseCreate,
    RequestStatusEnum,
)


class DocumentRequestRepository:
    """Thread-safe in-memory repository for Document Requests."""

    def __init__(self, max_entries: int = 1000):
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._storage: OrderedDict[str, DocumentRequestResponse] = OrderedDict()

    def _generate_id(self) -> str:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        token = uuid.uuid4().hex[:6].upper()
        return f"DOCREQ-{timestamp_str}-{token}"

    def create(self, data: DocumentRequestCreate) -> DocumentRequestResponse:
        """Stores a new document request initiated by an auditor."""
        with self._lock:
            req_id = self._generate_id()
            now = datetime.now(timezone.utc)
            due = data.due_date or (now + timedelta(days=14))

            record = DocumentRequestResponse(
                id=req_id,
                case_id=data.case_id,
                provider_npi=data.provider_npi,
                provider_name=data.provider_name,
                provider_email=data.provider_email or f"provider-{data.provider_npi}@wct-health.com",
                requested_documents=data.requested_documents,
                instructions=data.instructions,
                status=RequestStatusEnum.REQUESTED,
                requested_by=data.requested_by,
                created_at=now,
                due_date=due,
                read_at=None,
                read_count=0,
                last_read_at=None,
                response_notes=None,
                responded_by=None,
                responded_at=None,
                attachments=[],
                reminders_sent=0,
                last_reminder_sent_at=None,
            )

            # Evict oldest if limit reached
            if len(self._storage) >= self._max_entries:
                self._storage.popitem(last=False)

            self._storage[req_id] = record
            return record

    def get(self, request_id: str) -> Optional[DocumentRequestResponse]:
        """Retrieves a single request by unique ID."""
        with self._lock:
            return self._storage.get(request_id)

    def list_all(self) -> List[DocumentRequestResponse]:
        """Returns all document requests ordered by creation (newest first)."""
        with self._lock:
            return list(reversed(self._storage.values()))

    def list_by_case(self, case_id: str) -> List[DocumentRequestResponse]:
        """Returns all document requests for a specific case."""
        with self._lock:
            return [
                req for req in reversed(self._storage.values())
                if req.case_id.upper() == case_id.upper()
            ]

    def list_by_provider(self, provider_npi: str) -> List[DocumentRequestResponse]:
        """Returns all document requests directed to a specific provider NPI."""
        with self._lock:
            return [
                req for req in reversed(self._storage.values())
                if req.provider_npi == provider_npi
            ]

    def record_read(self, request_id: str) -> Optional[DocumentRequestResponse]:
        """
        Records a read receipt when a provider views or opens the request.
        Transitions status from REQUESTED -> VIEWED.
        """
        with self._lock:
            req = self._storage.get(request_id)
            if not req:
                return None

            now = datetime.now(timezone.utc)
            new_status = req.status
            if req.status == RequestStatusEnum.REQUESTED:
                new_status = RequestStatusEnum.VIEWED

            first_read = req.read_at or now

            updated = req.model_copy(
                update={
                    "status": new_status,
                    "read_at": first_read,
                    "read_count": req.read_count + 1,
                    "last_read_at": now,
                }
            )
            self._storage[request_id] = updated
            return updated

    def submit_response(
        self,
        request_id: str,
        response_data: DocumentResponseCreate,
    ) -> Optional[DocumentRequestResponse]:
        """
        Records the provider's submitted records, notes, and attachments.
        Transitions status to RESPONDED.
        """
        with self._lock:
            req = self._storage.get(request_id)
            if not req:
                return None

            now = datetime.now(timezone.utc)
            updated = req.model_copy(
                update={
                    "status": RequestStatusEnum.RESPONDED,
                    "response_notes": response_data.response_notes,
                    "responded_by": response_data.responded_by,
                    "responded_at": now,
                    "attachments": response_data.attachments,
                }
            )
            self._storage[request_id] = updated
            return updated

    def record_reminder_sent(self, request_id: str) -> Optional[DocumentRequestResponse]:
        """Increments reminder count and records timestamp."""
        with self._lock:
            req = self._storage.get(request_id)
            if not req:
                return None

            now = datetime.now(timezone.utc)
            updated = req.model_copy(
                update={
                    "reminders_sent": req.reminders_sent + 1,
                    "last_reminder_sent_at": now,
                }
            )
            self._storage[request_id] = updated
            return updated

    def cancel(self, request_id: str) -> Optional[DocumentRequestResponse]:
        """Cancels a pending document request."""
        with self._lock:
            req = self._storage.get(request_id)
            if not req:
                return None

            updated = req.model_copy(update={"status": RequestStatusEnum.CANCELLED})
            self._storage[request_id] = updated
            return updated

    def clear(self) -> None:
        """Clears all records (used for test teardown)."""
        with self._lock:
            self._storage.clear()


repository = DocumentRequestRepository(max_entries=settings.MAX_REQUESTS_ENTRIES)
