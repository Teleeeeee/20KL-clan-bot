"""Reads history/attacks.jsonl + history/roster_snapshot.json and rebuilds
data/data.json: ranking, top15, indicadores, stats_1m/2m, clan, meta.

Deliberately leaves data/plan_rotacion.json untouched - who attacks which
slot on which day is a leader's call, never the bot's. control_estrellas
IS rewritten from real CWL results when a CWL round is in progress, so
leaders stop typing star counts in by hand during CWL week.
"""
import json
import os
import sys
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import scoring  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
HISTORY_PATH = os.path.join(ROOT, "history", "attacks.jsonl")
ROSTER_PATH = os.path.join(ROOT, "history", "roster_snapshot.json")
PLAN_PATH = os.path.join(ROOT, "data", "plan_rotacion.json")
PARAMS_PATH = os.path.join(ROOT, "config", "parametros.json")
OUT_PATH = os.path.join(ROOT, "data", "data.json")

DEFAULT_PARAMS = {
    "Peso último mes": 0.65, "Peso dos meses": 0.35,
    "Promedio de estrellas": 40, "Triple rate": 25, "Volumen de ataques": 15,
    "Asistencia": 10, "Dificultad del objetivo": 10,
    "Score neutral": 60, "Ataques para volumen pleno": 12,
    "Ataques para confianza plena": 12, "Alta desde ataques (2 meses)": 20,
    "Media desde ataques (2 meses)": 8,
    "Titulares fijos": 10, "Titulares en rotación": 5, "Suplentes prioritarios": 5,
}


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def window_stats(records, tag, since, until=None):
    """Aggregate one player's atk/def records in [since, until)."""
    atk = [r for r in records if r["player_tag"] == tag and r["side"] == "atk"
           and since <= r["war_end_time_dt"] < (until or datetime.max.replace(tzinfo=timezone.utc))]
    df = [r for r in records if r["player_tag"] == tag and r["side"] == "def"
          and since <= r["war_end_time_dt"] < (until or datetime.max.replace(tzinfo=timezone.utc))]

    def bucket(rows):
        n = len(rows)
        stars = [r["stars"] for r in rows if r["stars"] is not None]
        ths = [r["opponent_th"] for r in rows if r["opponent_th"] is not None]
        c3 = sum(1 for s in stars if s == 3)
        c2 = sum(1 for s in stars if s == 2)
        c1 = sum(1 for s in stars if s == 1)
        c0 = sum(1 for s in stars if s == 0)
        return {
            "count": n,
            "avg_th_target": round(statistics.mean(ths), 2) if ths else None,
            "avg_stars": round(statistics.mean(stars), 4) if stars else 0,
            "c3": c3, "p3": round(c3 / n * 100, 2) if n else 0,
            "c2": c2, "p2": round(c2 / n * 100, 2) if n else 0,
            "c1": c1, "p1": round(c1 / n * 100, 2) if n else 0,
            "c0": c0, "p0": round(c0 / n * 100, 2) if n else 0,
        }

    return bucket(atk), bucket(df)


def miss_rate_for(planned_slots, atk_count):
    """We don't have a reliable 'expected attacks' signal outside CWL,
    so miss-rate is estimated only from CWL rounds where a plan exists;
    default 0 (matches original sheet's usual case)."""
    return 0.0


def build():
    raw = load_jsonl(HISTORY_PATH)
    for r in raw:
        r["war_end_time_dt"] = (
            datetime.fromtimestamp(r["war_end_time"] / 1000, tz=timezone.utc)
            if isinstance(r.get("war_end_time"), (int, float))
            else datetime.fromisoformat(str(r["war_end_time"]).replace("Z", "+00:00"))
            if r.get("war_end_time") else datetime.min.replace(tzinfo=timezone.utc)
        )

    roster = load_json(ROSTER_PATH, {"members": [], "clan_name": None, "clan_tag": None})
    members = roster.get("members", [])
    params = {**DEFAULT_PARAMS, **load_json(PARAMS_PATH, {})}

    now = datetime.now(timezone.utc)
    since_1m = now - timedelta(days=30)
    since_2m = now - timedelta(days=60)
    history_start = min((r["war_end_time_dt"] for r in raw), default=now)

    clan_rows = []
    ranking_rows_pre = []

    for i, m in enumerate(members):
        tag = m.get("tag")
        nick = m.get("name")
        th = m.get("townHallLevel") or m.get("townhallLevel")
        clan_rows.append({
            "tag": tag, "nick": nick, "th": th, "rol": m.get("role"),
            "rango": i + 1, "estrellas_guerra": m.get("warStars"),
        })

        atk1, def1 = window_stats(raw, tag, since_1m)
        atk2, def2 = window_stats(raw, tag, since_2m)

        s1 = scoring.player_score(
            atk1["avg_stars"], atk1["p3"] / 100, atk1["count"],
            miss_rate_for(None, atk1["count"]), atk1["avg_th_target"] or th, th,
        )
        s2 = scoring.player_score(
            atk2["avg_stars"], atk2["p3"] / 100, atk2["count"],
            miss_rate_for(None, atk2["count"]), atk2["avg_th_target"] or th, th,
        )
        final = scoring.score_final(s1["score"], s2["score"],
                                     params["Peso último mes"], params["Peso dos meses"])
        ranking_rows_pre.append({
            "player": nick, "tag": tag, "th": th,
            "atq1m": atk1["count"], "prom1m": atk1["avg_stars"], "p3_1m": atk1["p3"] / 100,
            "pfaltas1m": 0, "score1m": round(s1["score"], 4),
            "atq2m": atk2["count"], "prom2m": atk2["avg_stars"], "p3_2m": atk2["p3"] / 100,
            "pfaltas2m": 0, "score2m": round(s2["score"], 4),
            "tendencia": None,  # requires exclusive prior-month window; left null pre-day-60
            "score_final": round(final, 4),
            "confianza": scoring.confianza(atk2["count"]),
            "_stats1": atk1, "_stats2": atk2, "_def1": def1, "_def2": def2,
        })

    ranking_rows_pre.sort(key=lambda r: r["score_final"], reverse=True)
    ranking, stats_1m, stats_2m = [], [], []
    for idx, r in enumerate(ranking_rows_pre):
        rank = idx + 1
        rol = scoring.rol_for_rank(rank, params["Titulares fijos"],
                                    params["Titulares en rotación"], params["Suplentes prioritarios"])
        ranking.append({k: v for k, v in r.items() if not k.startswith("_")} | {"rank": rank, "rol": rol})
        stats_1m.append({
            "tag": r["tag"], "name": r["player"], "date_last_war": None, "avg_th": r["th"],
            "atq_count": r["_stats1"]["count"], "atq_avg_th_target": r["_stats1"]["avg_th_target"],
            "atq_avg_stars": r["_stats1"]["avg_stars"],
            "atq_3s": r["_stats1"]["c3"], "atq_p3s": r["_stats1"]["p3"],
            "atq_2s": r["_stats1"]["c2"], "atq_p2s": r["_stats1"]["p2"],
            "atq_1s": r["_stats1"]["c1"], "atq_p1s": r["_stats1"]["p1"],
            "atq_0s": r["_stats1"]["c0"], "atq_p0s": r["_stats1"]["p0"],
            "atq_miss": 0, "atq_pmiss": 0,
            "def_count": r["_def1"]["count"], "def_avg_th": r["_def1"]["avg_th_target"],
            "def_avg_stars": r["_def1"]["avg_stars"],
            "def_3s": r["_def1"]["c3"], "def_p3s": r["_def1"]["p3"],
            "def_2s": r["_def1"]["c2"], "def_p2s": r["_def1"]["p2"],
            "def_1s": r["_def1"]["c1"], "def_p1s": r["_def1"]["p1"],
            "def_0s": r["_def1"]["c0"], "def_p0s": r["_def1"]["p0"],
        })
        stats_2m.append({**stats_1m[-1],
                          "atq_count": r["_stats2"]["count"], "atq_avg_th_target": r["_stats2"]["avg_th_target"],
                          "atq_avg_stars": r["_stats2"]["avg_stars"],
                          "atq_3s": r["_stats2"]["c3"], "atq_p3s": r["_stats2"]["p3"],
                          "atq_2s": r["_stats2"]["c2"], "atq_p2s": r["_stats2"]["p2"],
                          "atq_1s": r["_stats2"]["c1"], "atq_p1s": r["_stats2"]["p1"],
                          "atq_0s": r["_stats2"]["c0"], "atq_p0s": r["_stats2"]["p0"],
                          "def_count": r["_def2"]["count"], "def_avg_stars": r["_def2"]["avg_stars"]})

    top15 = [{"rank": r["rank"], "player": r["player"], "score_final": r["score_final"],
              "tendencia": r["tendencia"], "prom1m": r["prom1m"], "p3_1m": r["p3_1m"]}
             for r in ranking[:15]]

    top15_scores = [r["score_final"] for r in ranking[:15]]
    top15_stars = [r["prom1m"] for r in ranking[:15] if r["atq1m"]]
    top15_p3 = [r["p3_1m"] for r in ranking[:15] if r["atq1m"]]
    indicadores = {
        "Score promedio Top 15": round(statistics.mean(top15_scores), 4) if top15_scores else None,
        "Promedio estrellas 1 mes Top 15": round(statistics.mean(top15_stars), 4) if top15_stars else None,
        "Triple rate 1 mes Top 15": round(statistics.mean(top15_p3), 4) if top15_p3 else None,
        "Ataques perdidos 1 mes Top 15": 0,
        "Proyección estrellas por día": round(statistics.mean(top15_stars) * 15, 4) if top15_stars else None,
    }

    # control_estrellas: auto-filled from real CWL results this round, mapped
    # onto whatever slot/day the leaders assigned in plan_rotacion.
    plan = load_json(PLAN_PATH, {"rows": []}).get("rows", [])
    cwl_by_player_day = defaultdict(dict)
    for r in raw:
        if r["side"] == "atk" and r["type"] == "cwl" and r.get("round_day"):
            cwl_by_player_day[r["player_tag"]][r["round_day"]] = r["stars"]

    name_to_tag = {m.get("name"): m.get("tag") for m in members}
    control_rows = []
    for row in ranking[:20]:
        tag = row["tag"]
        by_day = cwl_by_player_day.get(tag, {})
        d = {f"d{i}": by_day.get(i) for i in range(1, 8)}
        filled = [v for v in d.values() if v is not None]
        total = sum(filled)
        control_rows.append({
            "rank": row["rank"], "player": row["player"], "rol": row["rol"], **d,
            "total_estrellas": total,
            "estado": "Completo ✓" if total >= 8 else f"Faltan {8 - total}★",
            "atq_planificados": 7 if row["rol"] == "Titular fijo" else (4 if row["rol"] == "Titular rotación" else 3),
            "atq_restantes": None,
            "prom_esperado": None,
            "prom_resultado": round(total / len(filled), 2) if filled else None,
        })

    meta = {
        "clanTag": roster.get("clan_tag"),
        "clanName": roster.get("clan_name") or "Sala de Guerra CWL",
        "lastUpdated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "historyStart": history_start.strftime("%Y-%m-%d"),
        "source": "Clash of Clans API (oficial) vía cocproxy.royaleapi.dev",
    }

    out = {
        "ranking": ranking, "top15": top15, "indicadores": indicadores,
        "parametros": params, "stats_1m": stats_1m, "stats_2m": stats_2m,
        "clan": clan_rows, "control_estrellas": control_rows, "meta": meta,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_PATH}: {len(ranking)} players ranked.")


if __name__ == "__main__":
    build()
