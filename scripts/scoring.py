"""Reconstructed from the original CWL Manager spreadsheet (Parametros +
Cálculo CWL sheets), verified to reproduce its scores exactly:

  raw      = 40*(avg_stars/3) + 25*triple_rate + 15*min(attacks/12, 1)
             + 10*(1 - miss_rate) + 10*(avg_target_th/own_th)
  w        = min(attacks/12, 1)                      # sample-size weight
  score    = 60*(1 - w) + w*raw                       # shrinks to neutral 60
  calidad  = (raw - 15*min(attacks/12,1)) / 85 * 100   # quality w/o volume or shrink
  score_final = 0.65*score_1m + 0.35*score_2m
  tendencia   = calidad_1m - calidad_mes_anterior      # mes anterior = days 31-60 only

Confianza: "Alta" if attacks_2m >= 20, "Media" if >= 8, else "Baja".
Roles: rank 1-10 Titular fijo, 11-15 Titular rotación, 16-20 Suplente
prioritario, 21+ Reserva (matches "Titulares fijos"=10/"...rotación"=5/
"Suplentes prioritarios"=5 in Parametros).
"""

NEUTRAL_SCORE = 60
FULL_SAMPLE = 12
W_STARS, W_TRIPLE, W_VOLUME, W_ASSIST, W_DIFF = 40, 25, 15, 10, 10
QUALITY_DENOM = W_STARS + W_TRIPLE + W_ASSIST + W_DIFF  # 85


def player_score(avg_stars, triple_rate, attacks, miss_rate, avg_target_th, own_th):
    if attacks <= 0 or not own_th:
        return {"score": NEUTRAL_SCORE, "calidad": None, "raw": None, "w": 0}
    w = min(attacks / FULL_SAMPLE, 1)
    diff_ratio = (avg_target_th / own_th) if own_th else 1
    raw = (
        W_STARS * (avg_stars / 3)
        + W_TRIPLE * triple_rate
        + W_VOLUME * w
        + W_ASSIST * (1 - miss_rate)
        + W_DIFF * diff_ratio
    )
    score = NEUTRAL_SCORE * (1 - w) + w * raw
    calidad = (raw - W_VOLUME * w) / QUALITY_DENOM * 100
    return {"score": score, "calidad": calidad, "raw": raw, "w": w}


def score_final(score_1m, score_2m, peso_1m=0.65, peso_2m=0.35):
    return peso_1m * score_1m + peso_2m * score_2m


def confianza(attacks_2m):
    if attacks_2m >= 20:
        return "Alta"
    if attacks_2m >= 8:
        return "Media"
    return "Baja"


def rol_for_rank(rank, fijos=10, rotacion=5, suplentes=5):
    if rank <= fijos:
        return "Titular fijo"
    if rank <= fijos + rotacion:
        return "Titular rotación"
    if rank <= fijos + rotacion + suplentes:
        return "Suplente prioritario"
    return "Reserva"
