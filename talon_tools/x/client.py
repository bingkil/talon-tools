"""Async HTTP client for X GraphQL endpoints."""

from __future__ import annotations

import json
import logging

import httpx

from .auth import load_cookies, build_headers
from .endpoints import (
    BASE_URL,
    HOME_TIMELINE_QUERY_ID,
    SEARCH_TIMELINE_QUERY_ID,
    TWEET_DETAIL_QUERY_ID,
    features,
    field_toggles,
    home_timeline_vars,
    search_timeline_vars,
    tweet_detail_vars,
)

log = logging.getLogger(__name__)


class XClient:
    """Cookie-based async HTTP client for X's internal GraphQL API."""

    def __init__(self) -> None:
        cookies = load_cookies()
        self._ct0 = cookies["ct0"]
        self._cookies = cookies
        self._headers = build_headers(self._ct0)

    async def _get(self, query_id: str, operation: str, variables: dict) -> dict:
        """Execute a GraphQL GET request."""
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features()),
        }
        url = f"{BASE_URL}/{query_id}/{operation}"

        async with httpx.AsyncClient(
            headers=self._headers,
            cookies=self._cookies,
            timeout=30,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, params=params)

        return self._check(resp)

    async def _post(self, query_id: str, operation: str, variables: dict, *, toggles: bool = False) -> dict:
        """Execute a GraphQL POST request (used when query params would exceed URL length)."""
        body: dict = {
            "variables": variables,
            "features": features(),
        }
        if toggles:
            body["fieldToggles"] = field_toggles()
        url = f"{BASE_URL}/{query_id}/{operation}"

        async with httpx.AsyncClient(
            headers=self._headers,
            cookies=self._cookies,
            timeout=30,
            follow_redirects=True,
        ) as client:
            resp = await client.post(url, json=body)

        return self._check(resp)

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        if resp.status_code == 429:
            raise RuntimeError("X rate limit hit — try again later")
        if resp.status_code == 401:
            raise RuntimeError("X auth failed — cookies may be expired, re-extract from browser")
        resp.raise_for_status()
        return resp.json()

    async def get_home_timeline(self, count: int = 20) -> dict:
        """Fetch home timeline."""
        return await self._get(
            HOME_TIMELINE_QUERY_ID, "HomeTimeline", home_timeline_vars(count)
        )

    async def search(self, query: str, count: int = 20) -> dict:
        """Search tweets."""
        return await self._post(
            SEARCH_TIMELINE_QUERY_ID, "SearchTimeline", search_timeline_vars(query, count),
            toggles=True,
        )

    async def get_tweet(self, tweet_id: str) -> dict:
        """Fetch a single tweet by ID."""
        return await self._get(
            TWEET_DETAIL_QUERY_ID, "TweetDetail", tweet_detail_vars(tweet_id)
        )
