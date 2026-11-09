"""Elección del grupo para la siguiente publicación (spec §6)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .grupos import Grupo
from .historial import Historial


def elegir_grupo(grupos: list[Grupo], historial: Historial, ahora: datetime, minutos: int,
                 excluir: set[str], rng: random.Random, cuenta: str | None = None) -> Grupo | None:
    limite = ahora - timedelta(minutes=minutos)
    ultimas = historial.ultimas_publicaciones(cuenta)
    candidatos: list[tuple[datetime | None, Grupo]] = []
    for g in grupos:
        if not g.activo or g.link in excluir:
            continue
        ultima = ultimas.get(g.link)
        if ultima is not None and ultima > limite:
            continue
        candidatos.append((ultima, g))
    if not candidatos:
        return None
    nunca = [g for u, g in candidatos if u is None]
    if nunca:
        return rng.choice(nunca)
    mas_antigua = min(u for u, _ in candidatos)
    return rng.choice([g for u, g in candidatos if u == mas_antigua])
