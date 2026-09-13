"""One immutable destination and credential snapshot per Flask application."""
from __future__ import annotations

import os
from dataclasses import dataclass

from flask import current_app
import requests

from .hq_client import HQClient

@dataclass
class CoreConfiguration:
    base_url: str
    platform_secret: str
    client: HQClient | None = None


def configure_core(app, base_url=None):
    previous = app.extensions.get('aj_core')
    if previous is not None:
        if base_url and previous.base_url != base_url.rstrip('/'):
            raise ValueError('Core configuration already initialized for this app')
        return previous
    config = CoreConfiguration(
        (base_url or app.config.get('AJ_HQ_BASE') or os.environ.get('AJ_HQ_BASE') or 'https://aj-hq.up.railway.app').rstrip('/'),
        app.config.get('PLATFORM_SECRET', os.environ.get('PLATFORM_SECRET', '')),
    )
    app.extensions['aj_core'] = config
    return config


def core_config():
    return configure_core(current_app)


def core_client():
    config = core_config()
    if config.client is None:
        # The stateless requests transport avoids retaining upstream cookies;
        # every call still uses HQClient's shared bounded response handling.
        config.client = HQClient(config.base_url, config.platform_secret, session=requests)
    return config.client
