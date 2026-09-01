"""Extracao de cambio PTAX venda na API de dados abertos do Banco Central (SGS).

Serie 1 = dolar comercial, venda. A API entrega apenas dias uteis, o que obriga
forward-fill para pagamentos em fim de semana e feriado. O resultado e cacheado
em disco: o pipeline precisa ser idempotente e reprodutivel, e depender de rede
viva a cada execucao violaria as duas coisas.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date, timedelta

from config import BCB_SERIE_DOLAR_VENDA, BCB_URL, FX_CACHE, FX_FIM, FX_INI

log = logging.getLogger(__name__)

_JANELA_DIAS = 3650   # a API limita o intervalo por requisicao; 10 anos e seguro
_TIMEOUT = 45
_TENTATIVAS = 3


class FXIndisponivelError(RuntimeError):
    """Cambio nao pudo ser obtido nem da API nem do cache."""


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _buscar_bcb(ini: date, fim: date) -> list[dict]:
    url = (f"{BCB_URL.format(serie=BCB_SERIE_DOLAR_VENDA)}"
           f"?formato=json&dataInicial={_fmt(ini)}&dataFinal={_fmt(fim)}")
    ultimo_erro: Exception | None = None
    for tentativa in range(1, _TENTATIVAS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tellus-case/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(url, resp.status, "status inesperado", resp.headers, None)
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            ultimo_erro = exc
            log.warning("BCB tentativa %d/%d falhou: %s", tentativa, _TENTATIVAS, exc)
    raise FXIndisponivelError(f"API do BCB indisponivel apos {_TENTATIVAS} tentativas") from ultimo_erro


def _validar(cot: dict[str, float]) -> None:
    """Barreira de sanidade: cambio fora de faixa plausivel derruba o pipeline.

    Preferimos falhar alto a publicar receita convertida por taxa corrompida.
    """
    if not cot:
        raise FXIndisponivelError("serie de cambio vazia")
    fora = {d: v for d, v in cot.items() if not (2.0 <= v <= 12.0)}
    if fora:
        raise FXIndisponivelError(f"cotacoes fora da faixa plausivel 2..12: {list(fora.items())[:5]}")
    log.info("cambio validado: %d dias uteis, min=%.4f max=%.4f",
             len(cot), min(cot.values()), max(cot.values()))


def carregar_ptax(forcar_refresh: bool = False) -> dict[str, float]:
    """Retorna {'YYYY-MM-DD': taxa} apenas para dias uteis publicados.

    Usa cache em disco quando disponivel. A idempotencia do pipeline depende
    disso: duas execucoes seguidas convertem com exatamente a mesma taxa.
    """
    if FX_CACHE.exists() and not forcar_refresh:
        cot = json.loads(FX_CACHE.read_text(encoding="utf-8"))
        log.info("cambio lido do cache (%s): %d observacoes", FX_CACHE.name, len(cot))
        _validar(cot)
        return cot

    log.info("buscando PTAX venda (SGS serie %d) de %s a %s", BCB_SERIE_DOLAR_VENDA, FX_INI, FX_FIM)
    cot: dict[str, float] = {}
    ini = FX_INI
    while ini <= FX_FIM:
        fim = min(ini + timedelta(days=_JANELA_DIAS), FX_FIM)
        for reg in _buscar_bcb(ini, fim):
            d, m, y = reg["data"].split("/")
            cot[f"{y}-{m}-{d}"] = float(reg["valor"])
        ini = fim + timedelta(days=1)

    _validar(cot)
    FX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FX_CACHE.write_text(json.dumps(cot, indent=0, sort_keys=True), encoding="utf-8")
    log.info("cambio persistido em %s", FX_CACHE)
    return cot


def serie_diaria_preenchida(cot: dict[str, float]) -> list[tuple[str, float, bool]]:
    """Expande a serie para todos os dias do calendario com forward-fill.

    Retorna (data_iso, taxa, foi_preenchida). O flag existe para que qualquer
    numero convertido possa ser rastreado ate a origem da taxa usada.
    """
    if not cot:
        raise FXIndisponivelError("serie vazia, nada a preencher")
    dias = sorted(cot)
    atual = date.fromisoformat(dias[0])
    ultimo = date.fromisoformat(dias[-1])
    taxa_vigente = cot[dias[0]]
    saida: list[tuple[str, float, bool]] = []
    while atual <= ultimo:
        iso = atual.isoformat()
        if iso in cot:
            taxa_vigente = cot[iso]
            saida.append((iso, taxa_vigente, False))
        else:
            saida.append((iso, taxa_vigente, True))
        atual += timedelta(days=1)
    preenchidos = sum(1 for _, _, f in saida if f)
    log.info("serie diaria: %d dias, %d por forward-fill (%.1f%%)",
             len(saida), preenchidos, 100 * preenchidos / len(saida))
    return saida
