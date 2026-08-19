"""Provider abstraction for fetching an Instagram account's follower count.

Each adapter takes a username and API key and returns an int follower count,
raising ProviderError on failure. get_provider() selects an adapter by name
and wraps it with a shared retry-with-backoff policy.
"""
import hashlib
import logging
import time
from typing import Callable

import requests

import config

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when a provider fails to return a follower count."""


def fetch_hikerapi(username: str, api_key: str) -> int:
    """Fetch follower count via HikerAPI.

    Docs: https://hikerapi.com/docs -- endpoint and field name below are the
    best-known shape at time of writing but have NOT been verified against a
    live key. Confirm both against the real API response before relying on
    this in production.
    """
    url = "https://api.hikerapi.com/v1/user/by/username"
    headers = {"x-access-key": api_key}
    resp = requests.get(url, headers=headers, params={"username": username}, timeout=15)
    if not resp.ok:
        raise ProviderError(f"HikerAPI returned {resp.status_code} for {username}: {resp.text}")
    data = resp.json()
    # TODO: confirm exact field name/path in HikerAPI's response before going live.
    follower_count = data.get("follower_count")
    if follower_count is None:
        raise ProviderError(f"HikerAPI response missing follower_count for {username}: {data}")
    return int(follower_count)


def fetch_apify(username: str, api_key: str) -> int:
    """Fetch follower count via Apify's Instagram Profile Scraper actor.

    Docs: https://apify.com/apify/instagram-profile-scraper -- run-sync
    Actor: apify/instagram-profile-scraper (id dSCLg0C3YEZ83HzYX). Confirmed
    against a live run: input is {"usernames": [...]}, response is a list of
    profile objects each containing a "followersCount" field.
    """
    actor_id = "apify~instagram-profile-scraper"
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    resp = requests.post(
        url,
        params={"token": api_key},
        json={"usernames": [username]},
        timeout=60,
    )
    if not resp.ok:
        raise ProviderError(f"Apify returned {resp.status_code} for {username}: {resp.text}")
    items = resp.json()
    if not items:
        raise ProviderError(f"Apify returned no data for {username}")
    follower_count = items[0].get("followersCount")
    if follower_count is None:
        raise ProviderError(f"Apify response missing followersCount for {username}: {items[0]}")
    return int(follower_count)


def fetch_mock(username: str, api_key: str = "") -> int:
    """Deterministic fake follower count derived from the username's hash.

    Lets the whole pipeline (fetch -> history -> report -> sheets) be
    exercised locally without any provider account or API key.
    """
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    base = int(digest[:8], 16) % 50_000_000
    # Add small day-to-day drift so reports show non-zero deltas on reruns.
    drift = int(digest[8:10], 16) - 128
    return max(base + drift * int(time.time() // 86400) % 5000, 0)


_ADAPTERS: dict[str, Callable[[str, str], int]] = {
    "hikerapi": fetch_hikerapi,
    "apify": fetch_apify,
    "mock": fetch_mock,
}


def get_provider(name: str | None = None) -> Callable[[str], int]:
    """Return a retry-wrapped fetch function: fetch(username) -> follower_count."""
    provider_name = (name or config.PROVIDER).lower()
    if provider_name not in _ADAPTERS:
        raise ValueError(
            f"Unknown provider '{provider_name}'. Valid options: {list(_ADAPTERS)}"
        )
    adapter = _ADAPTERS[provider_name]

    def fetch(username: str) -> int:
        last_error: Exception | None = None
        for attempt in range(1, config.RETRY_ATTEMPTS + 1):
            try:
                return adapter(username, config.PROVIDER_API_KEY)
            except (ProviderError, requests.RequestException) as exc:
                last_error = exc
                logger.warning(
                    "Provider '%s' failed for %s (attempt %d/%d): %s",
                    provider_name, username, attempt, config.RETRY_ATTEMPTS, exc,
                )
                if attempt < config.RETRY_ATTEMPTS:
                    time.sleep(config.RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
        raise ProviderError(f"All retries failed for {username}") from last_error

    return fetch
