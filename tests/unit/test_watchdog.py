import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.watchdog import checks
from app.db.models import RawEvent, Document, ExtractionStatus
from app.config import settings

@pytest.mark.asyncio
async def test_check_dependencies_success():
    db = AsyncMock()
    redis_client = MagicMock()
    
    redis_client.ping.return_value = True
    
    # We mock minio_client in checks using patch?
    # Or rely on integration if difficult.
    # Unit testing module level globals is tricky without patch.
    # I'll use unittest.mock.patch
    with pytest.MonkeyPatch.context() as m:
        # Mock MinIO
        mock_minio = MagicMock()
        mock_minio.client.bucket_exists.return_value = True
        mock_minio.bucket = "test-bucket"
        m.setattr(checks, "minio_client", mock_minio)
        
        status = await checks.check_dependencies(db, redis_client)
        assert status["postgres"] is True
        assert status["redis"] is True
        assert status["minio"] is True

@pytest.mark.asyncio
async def test_check_ingestion_health_signature_fails():
    db = AsyncMock()
    
    # Mock result for signature fails
    # The function calls execute twice.
    # 1. Total count (scalar)
    # 2. Sig fails (scalar)
    
    # We can mock side_effect for execute
    mock_res_total = MagicMock()
    mock_res_total.scalar.return_value = 100
    
    mock_res_sig = MagicMock()
    mock_res_sig.scalar.return_value = 10 # > 5 threshold
    
    db.execute.side_effect = [mock_res_total, mock_res_sig]
    
    alerts = await checks.check_ingestion_health(db)
    
    assert len(alerts) == 1
    assert alerts[0]["type"] == "ingestion_signature_failures"
    assert alerts[0]["count"] == 10

@pytest.mark.asyncio
async def test_check_document_health_stalled():
    db = AsyncMock()
    
    # Mock 1: Pending IDs
    mock_res_pending = MagicMock()
    mock_res_pending.scalars().all.return_value = [1, 2, 3] # 3 stalled
    
    # Mock 2: Failed count
    mock_res_failed = MagicMock()
    mock_res_failed.scalar.return_value = 0
    
    db.execute.side_effect = [mock_res_pending, mock_res_failed]
    
    alerts, stalled = await checks.check_document_health(db)
    
    assert len(alerts) == 1
    assert alerts[0]["type"] == "stalled_documents"
    assert len(stalled) == 3

@pytest.mark.asyncio
async def test_check_queue_health_backlog():
    redis_client = MagicMock()
    redis_client.llen.return_value = 1000 # > 500 default
    
    alerts = await checks.check_queue_health(redis_client)
    
    assert len(alerts) == 1
    assert alerts[0]["type"] == "queue_backlog"
