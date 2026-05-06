"""Channels DVR settings and connection test endpoints."""

from fastapi import APIRouter

from teamarr.database import get_db

from .models import (
    ChannelsDVRConnectionTestRequest,
    ChannelsDVRConnectionTestResponse,
    ChannelsDVRSettingsModel,
    ChannelsDVRSettingsUpdate,
    unmask_or_skip,
)

router = APIRouter()


@router.get("/settings/channelsdvr", response_model=ChannelsDVRSettingsModel)
def get_channelsdvr_settings():
    """Get Channels DVR integration settings."""
    from teamarr.database.settings import get_channelsdvr_settings

    with get_db() as conn:
        settings = get_channelsdvr_settings(conn)

    return ChannelsDVRSettingsModel(
        enabled=settings.enabled,
        url=settings.url,
        source_name=settings.source_name,
        username=settings.username,
        password=settings.password,
    )


@router.put("/settings/channelsdvr", response_model=ChannelsDVRSettingsModel)
def update_channelsdvr_settings(update: ChannelsDVRSettingsUpdate):
    """Update Channels DVR integration settings."""
    from teamarr.database.settings import (
        get_channelsdvr_settings,
        update_channelsdvr_settings,
    )

    with get_db() as conn:
        update_channelsdvr_settings(
            conn,
            enabled=update.enabled,
            url=update.url,
            source_name=update.source_name,
            username=update.username,
            password=unmask_or_skip(update.password),
        )

    with get_db() as conn:
        settings = get_channelsdvr_settings(conn)

    return ChannelsDVRSettingsModel(
        enabled=settings.enabled,
        url=settings.url,
        source_name=settings.source_name,
        username=settings.username,
        password=settings.password,
    )


@router.post("/channelsdvr/test", response_model=ChannelsDVRConnectionTestResponse)
def test_channelsdvr_connection(
    request: ChannelsDVRConnectionTestRequest | None = None,
):
    """Test connection to Channels DVR server.

    If no parameters provided, tests with saved settings.
    Accepts optional url/source_name/username/password overrides.
    """
    from teamarr.channelsdvr.client import ChannelsDVRClient
    from teamarr.database.settings import get_channelsdvr_settings

    with get_db() as conn:
        saved = get_channelsdvr_settings(conn)

    url = (request.url if request and request.url else saved.url) or ""
    source_name = (
        request.source_name if request and request.source_name else saved.source_name
    ) or ""
    username = (
        request.username if request and request.username else saved.username
    ) or ""
    password = (
        request.password if request and request.password else saved.password
    ) or ""

    if not url:
        return ChannelsDVRConnectionTestResponse(
            success=False,
            error="No Channels DVR URL configured",
        )

    client = ChannelsDVRClient(
        base_url=url,
        source_name=source_name,
        username=username,
        password=password,
    )
    result = client.test_connection()

    return ChannelsDVRConnectionTestResponse(
        success=result.get("success", False),
        server_version=result.get("server_version"),
        source_name=result.get("source_name"),
        error=result.get("error"),
    )
