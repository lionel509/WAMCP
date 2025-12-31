import pytest
import uuid
from datetime import datetime, timedelta
from app.db.models import Document, ExtractionStatus, AuditLog, WatchdogRun
from app.watchdog import checks, remediation
from sqlalchemy import select, text
from app.config import settings

@pytest.mark.asyncio
async def test_watchdog_integration_stalled_docs(db_session):
    # Setup: Create a stalled document
    stalled_doc_id = uuid.uuid4()
    from datetime import timezone
    now = datetime.now(timezone.utc)
    stalled_doc = Document(
        id=stalled_doc_id,
        message_id="test_msg",
        doc_type="other",
        storage_key_raw="pending/key",
        extraction_status=ExtractionStatus.PENDING,
        created_at=now - timedelta(minutes=settings.WATCHDOG_STUCK_MESSAGE_MINUTES + 5)
    )
    db_session.add(stalled_doc)
    await db_session.commit()
    
    # Check
    alerts, stalled_ids = await checks.check_document_health(db_session)
    
    assert len(alerts) > 0
    assert alerts[0]["type"] == "stalled_documents"
    assert str(stalled_doc_id) in stalled_ids
    
    # Remediation
    await remediation.reenqueue_stalled_documents(db_session, stalled_ids)
    
    # Verify Audit Log
    stmt = select(AuditLog).where(
        AuditLog.actor == "watchdog", 
        AuditLog.action == "reenqueue_documents"
    )
    res = await db_session.execute(stmt)
    audit = res.scalar()
    
    assert audit is not None
    assert str(stalled_doc_id) in audit.metadata_json["ids"]

@pytest.mark.asyncio
async def test_watchdog_run_log(db_session):
    # Manually create a run log to test model
    run = WatchdogRun(status_json={"test": "ok"})
    db_session.add(run)
    await db_session.commit()
    
    stmt = select(WatchdogRun).where(WatchdogRun.id == run.id)
    res = await db_session.execute(stmt)
    assert res.scalar() is not None
