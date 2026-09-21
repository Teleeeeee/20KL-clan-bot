# CWL sync bot

Consulta la API oficial de Clash of Clans cada 30 minutos (vía el proxy
`cocproxy.royaleapi.dev`, necesario porque GitHub Actions no tiene IP fija),
acumula cada ataque que ve en `history/attacks.jsonl` (la API no guarda
historial — solo muestra la guerra en curso, así que hay que ir
"escuchando" para construirlo) y recalcula `data/data.json` con el
ranking, las estadísticas de 1 y 2 meses, el roster del clan y (durante
CWL) los resultados reales día por día.

## Ya configurado
- Secret `COC_API_KEY`: tu key de developer.clashofclans.com, con la IP del
  proxy (`45.79.218.79`) whitelisteada.
- Secret `CLAN_TAG`: `2VJ2LPY8` (sin `#`).

## Qué corre solo
`.github/workflows/sync.yml` corre cada 30 minutos:
1. `scripts/poll_wars.py` — pega contra `/currentwar` y, si hay CWL activa,
   `/currentwar/leaguegroup` + cada guerra del grupo. Guarda cada ataque
   nuevo (propio y en defensa) en `history/attacks.jsonl`, sin duplicar.
   También pisa `history/roster_snapshot.json` con el roster actual.
2. `scripts/build_dashboard.py` — con ese historial, recalcula ventanas de
   30 y 60 días por jugador, aplica la fórmula de scoring (ver
   `scripts/scoring.py` — reconstruida a partir de tu Excel original,
   verificada número por número) y escribe `data/data.json`.
3. Si algo cambió, lo commitea y pushea.

`data/plan_rotacion.json` (quién ataca en cada puesto/día) **nunca lo toca
el bot** — eso lo administran los líderes desde la web. `control_estrellas`
sí se recalcula solo durante una CWL activa, cruzando los resultados reales
con el plan cargado.

## Primeros días
La API no tiene historial: el bot arranca desde cero el día que lo prendés.
Vas a ver datos parciales las primeras ~4 semanas ("1 mes" se completa a
los 30 días, "2 meses" a los 60). Mientras tanto `meta.historyStart` en
`data.json` dice desde cuándo hay datos.

## Correrlo a mano
Actions → "Sync CWL data" → "Run workflow" (botón `workflow_dispatch`), por
si no querés esperar los 30 minutos para probar que ande.

## Ajustar la fórmula
Si cambiás pesos en `config/parametros.json` (mismo formato que la hoja
"Parámetros" del Excel), el próximo run los toma solos — no hace falta
tocar el código.
