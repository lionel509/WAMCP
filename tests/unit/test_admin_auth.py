import pytest
from fastapi import HTTPException

from app.api.admin import require_admin_api_key
from app.config import settings


@pytest.mark.asyncio
async def test_require_admin_api_key_missing():
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_admin_api_key_invalid():
    with pytest.raises(HTTPException) as exc:
        await require_admin_api_key("bad-key")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_api_key_valid():
    assert await require_admin_api_key(settings.admin_api_key)
