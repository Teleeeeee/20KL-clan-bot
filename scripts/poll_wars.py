"""Runs every ~30 min via GitHub Actions.

The Clash of Clans API has no history endpoint - /currentwar only shows
the war that's happening right now, and it disappears once the next war's
prep day starts. So this script's only job is to catch every attack while
it's still visible and append it, once, to an append-only log
(history/attacks.jsonl). build_dashboard.py later turns that log into
rolling 1/2-month stats and the CWL day-by-day results, the same way a
site like ClashSpot does by polling continuously.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import coc_api  # noqa: E402

CLAN_TAG = "#" + os.environ["CLAN_TAG"].lstrip("#")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "history", "attacks.jsonl")
ROSTER_PATH = os.path.join(os.path.dirname(__file__), "..", "history", "roster_snapshot.json")


def load_seen_keys():
    seen = set()
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    seen.add(rec["key"])
                except Exception:
                    continue
    return seen


def append_records(records):
    if not records:
        return
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def extract_attacks(war, clan_tag, war_type, round_day=None):
    """war: a currentwar-shaped dict with clan/opponent. Returns records for
    both our members' attacks (side=atk) and the opponent's attacks against
    our members (side=def), or [] if this war isn't ours or has no attack
    data yet."""
    if not war or war.get("state") not in ("inWar", "warEnded"):
        return []
    clan = war.get("clan", {})
    opponent = war.get("opponent", {})
    if clan.get("tag") == clan_tag:
        mine, theirs = clan, opponent
    elif opponent.get("tag") == clan_tag:
        mine, theirs = opponent, clan
    else:
        return []

    end_time = war.get("endTime")
    now = datetime.now(timezone.utc).isoformat()
    out = []

    def th_of(pool, tag):
        return next((m.get("townhallLevel") for m in pool.get("members", []) if m.get("tag") == tag), None)

    for member in mine.get("members", []):
        for atk in member.get("attacks", []):
            key = "|".join(["atk", war_type, str(end_time), member.get("tag"),
                             atk.get("defenderTag", ""), str(atk.get("order", ""))])
            out.append({
                "key": key, "side": "atk", "type": war_type,
                "war_end_time": end_time, "round_day": round_day,
                "player_tag": member.get("tag"), "player_name": member.get("name"),
                "player_th": member.get("townhallLevel"),
                "opponent_tag": atk.get("defenderTag"),
                "opponent_th": th_of(theirs, atk.get("defenderTag")),
                "stars": atk.get("stars"), "destruction": atk.get("destructionPercentage"),
                "fetched_at": now,
            })

    # Defense: the opponent's attacks, filtered to the ones that hit one of
    # our members (defenderTag in mine).
    my_tags = {m.get("tag") for m in mine.get("members", [])}
    my_th_by_tag = {m.get("tag"): m.get("townhallLevel") for m in mine.get("members", [])}
    for opp_member in theirs.get("members", []):
        for atk in opp_member.get("attacks", []):
            def_tag = atk.get("defenderTag")
            if def_tag not in my_tags:
                continue
            key = "|".join(["def", war_type, str(end_time), def_tag,
                             opp_member.get("tag", ""), str(atk.get("order", ""))])
            defender_name = next((m.get("name") for m in mine.get("members", []) if m.get("tag") == def_tag), None)
            out.append({
                "key": key, "side": "def", "type": war_type,
                "war_end_time": end_time, "round_day": round_day,
                "player_tag": def_tag, "player_name": defender_name,
                "player_th": my_th_by_tag.get(def_tag),
                "opponent_tag": opp_member.get("tag"),
                "opponent_th": opp_member.get("townhallLevel"),
                "stars": atk.get("stars"), "destruction": atk.get("destructionPercentage"),
                "fetched_at": now,
            })
    return out


def main():
    seen = load_seen_keys()
    new_records = []

    # --- regular war ---
    war = coc_api.get_current_war(CLAN_TAG)
    new_records += extract_attacks(war, CLAN_TAG, "regular")

    # --- CWL ---
    group = coc_api.get_cwl_group(CLAN_TAG)
    if group and group.get("state") in ("inWar", "warEnded", "preparation"):
        rounds = group.get("rounds", [])
        day = 0
        for rnd in rounds:
            war_tags = [t for t in rnd.get("warTags", []) if t and t != "#0"]
            if not war_tags:
                continue
            day += 1
            for war_tag in war_tags:
                cwl_war = coc_api.get_cwl_war(war_tag)
                new_records += extract_attacks(cwl_war, CLAN_TAG, "cwl", round_day=day)

    fresh = [r for r in new_records if r["key"] not in seen]
    # dedup within this batch too
    dedup, batch_seen = [], set()
    for r in fresh:
        if r["key"] in batch_seen:
            continue
        batch_seen.add(r["key"])
        dedup.append(r)

    append_records(dedup)
    print(f"Polled: {len(new_records)} attacks seen, {len(dedup)} new appended to history.")

    # --- roster snapshot (overwritten each run, not append-only) ---
    members = coc_api.get_clan_members(CLAN_TAG)
    clan_info = coc_api.get_clan(CLAN_TAG)
    with open(ROSTER_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "clan_name": clan_info.get("name") if clan_info else None,
            "clan_tag": CLAN_TAG,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "members": members,
        }, f, ensure_ascii=False, indent=2)
    print(f"Roster snapshot: {len(members)} members.")


if __name__ == "__main__":
    main()
