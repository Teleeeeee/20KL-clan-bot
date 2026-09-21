"""Thin client for the Clash of Clans API via the RoyaleAPI proxy.

The proxy exists because the official API requires a fixed allow-listed IP,
and CI runners (GitHub Actions) don't have one. cocproxy.royaleapi.dev
forwards to api.clashofclans.com from a fixed IP that's whitelisted on the
key instead.
"""
import os
import time
import urllib.parse
import requests

BASE_URL = os.environ.get("COC_API_BASE", "https://cocproxy.royaleapi.dev/v1")
API_KEY = os.environ["COC_API_KEY"]

_session = requests.Session()
_session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})


def _get(path, params=None, allow_404=False):
    url = BASE_URL + path
    for attempt in range(3):
        try:
            resp = _session.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code == 404 and allow_404:
            return None
        if resp.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if resp.status_code >= 500:
            time.sleep(3 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    return None


def tag_path(tag):
    """URL-encode a player/clan tag (#ABC123 -> %23ABC123)."""
    if not tag.startswith("#"):
        tag = "#" + tag
    return urllib.parse.quote(tag, safe="")


def get_clan(clan_tag):
    return _get(f"/clans/{tag_path(clan_tag)}")


def get_clan_members(clan_tag):
    data = _get(f"/clans/{tag_path(clan_tag)}/members")
    return data.get("items", []) if data else []


def get_current_war(clan_tag):
    """Regular (non-CWL) current war. Returns None if private or no war."""
    return _get(f"/clans/{tag_path(clan_tag)}/currentwar", allow_404=True)


def get_cwl_group(clan_tag):
    """Current CWL league group, or None if the clan isn't in a CWL round."""
    return _get(f"/clans/{tag_path(clan_tag)}/currentwar/leaguegroup", allow_404=True)


def get_cwl_war(war_tag):
    return _get(f"/clanwarleagues/wars/{tag_path(war_tag)}")
