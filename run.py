"""Ponto de entrada unico: python run.py roda tudo do zero.

    python run.py                 pipeline completo + checks + relatorio
    python run.py --forcar-fx     refaz a extracao de cambio na API do BCB
    python run.py --sem-relatorio so pipeline e checks
    python run.py --idempotencia  roda duas vezes e compara os resultados
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import checks          # noqa: E402
import pipeline        # noqa: E402
from config import DUCKDB_PATH, OUT_DIR  # noqa: E402


def configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-12s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def _assinatura_resultados(con) -> dict[str, tuple]:
    """Impressao digital das tabelas de consumo, para provar idempotencia."""
    tabelas = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE 'gold_%' ORDER BY table_name").fetchall()]
    assinatura = {}
    for t in tabelas:
        cols = [r[0] for r in con.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}' "
            "AND data_type IN ('DOUBLE','BIGINT','INTEGER','HUGEINT','DECIMAL') "
            "ORDER BY column_name").fetchall()]
        soma = 0.0
        if cols:
            expr = " + ".join(f"coalesce(sum({c}), 0)" for c in cols)
            soma = con.execute(f"SELECT {expr} FROM {t}").fetchone()[0] or 0.0
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        assinatura[t] = (n, round(float(soma), 6))
    return assinatura


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline de unit economics da Tellus")
    ap.add_argument("--forcar-fx", action="store_true", help="refaz extracao de cambio na API do BCB")
    ap.add_argument("--sem-relatorio", action="store_true", help="nao gera o HTML")
    ap.add_argument("--idempotencia", action="store_true", help="roda 2x e compara")
    ap.add_argument("-v", "--verboso", action="store_true")
    args = ap.parse_args()
    configurar_log(args.verboso)
    log = logging.getLogger("run")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 70)
    log.info("TELLUS | pipeline de unit economics | destino: %s", DUCKDB_PATH)
    log.info("=" * 70)

    con = pipeline.rodar(forcar_fx=args.forcar_fx)
    primeira = _assinatura_resultados(con) if args.idempotencia else None

    rel = checks.executar(con)

    if not args.sem_relatorio:
        import report
        caminho = report.gerar(con, rel)
        log.info("relatorio executivo: %s", caminho)

    if args.idempotencia:
        con.close()
        log.info("--- segunda execucao para prova de idempotencia ---")
        con2 = pipeline.rodar(forcar_fx=False)
        segunda = _assinatura_resultados(con2)
        divergencias = {t: (primeira.get(t), segunda.get(t))
                        for t in set(primeira) | set(segunda)
                        if primeira.get(t) != segunda.get(t)}
        if divergencias:
            log.error("IDEMPOTENCIA VIOLADA em %d tabelas: %s", len(divergencias), divergencias)
            return 2
        log.info("idempotencia confirmada: %d tabelas gold identicas nas duas execucoes", len(segunda))
        con2.close()
    else:
        con.close()

    if rel.falhas_bloqueantes:
        log.error("PIPELINE REPROVADO: %d checks bloqueantes falharam", len(rel.falhas_bloqueantes))
        for f in rel.falhas_bloqueantes:
            log.error("  - %s: %s", f.nome, f.detalhe)
        return 1

    log.info("pipeline aprovado. %d alertas registrados no relatorio.", len(rel.alertas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
