"""Geracao do relatorio executivo em HTML autocontido.

Restricao deliberada de arquitetura: zero dependencia externa. Nenhuma CDN,
nenhuma biblioteca de grafico, nenhuma chamada de rede em tempo de abertura.
Os graficos sao SVG gerado em Python e embutido no arquivo. O relatorio abre
com duplo clique, funciona offline e nao depende de nenhuma plataforma.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime

import duckdb

from config import DATA_CORTE, OUT_DIR, PERIODO_FIM, PERIODO_INI, PREMISSAS

log = logging.getLogger(__name__)

# Paleta com contraste suficiente em fundo claro e escuro.
AZUL, VERDE, VERMELHO, CINZA, AMBAR, ROXO = "#2563eb", "#059669", "#dc2626", "#6b7280", "#d97706", "#7c3aed"


# ----------------------------------------------------------------- formatacao
def brl(v, dec=0):
    if v is None:
        return "n/d"
    s = f"{abs(v):,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if v < 0 else ''}{s}"


def pct(v, dec=1):
    return "n/d" if v is None else f"{v * 100:.{dec}f}%".replace(".", ",")


def num(v, dec=1):
    return "n/d" if v is None else f"{v:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def esc(s):
    return html.escape(str(s if s is not None else ""))


# --------------------------------------------------------------------- SVG
def _eixo_y(vmin, vmax, n=5):
    if vmax == vmin:
        vmax = vmin + 1
    passo = (vmax - vmin) / n
    return [vmin + passo * i for i in range(n + 1)]


def svg_linhas(series, labels, titulo_y="", altura=300, largura=880, formatador=brl):
    """Grafico de linhas. series = [(nome, [valores], cor)]."""
    ml, mr, mt, mb = 78, 16, 16, 46
    pw, ph = largura - ml - mr, altura - mt - mb
    todos = [v for _, vs, _ in series for v in vs if v is not None]
    if not todos:
        return "<p>sem dados</p>"
    vmin, vmax = min(0, min(todos)), max(todos)
    ticks = _eixo_y(vmin, vmax)

    def x(i):
        return ml + (pw * i / max(1, len(labels) - 1))

    def y(v):
        return mt + ph - (ph * (v - vmin) / (vmax - vmin or 1))

    p = [f'<svg viewBox="0 0 {largura} {altura}" role="img" style="width:100%;height:auto">']
    for t in ticks:
        p.append(f'<line x1="{ml}" y1="{y(t):.1f}" x2="{ml+pw}" y2="{y(t):.1f}" stroke="{CINZA}" '
                 f'stroke-opacity="0.25" stroke-width="1"/>')
        p.append(f'<text x="{ml-8}" y="{y(t)+4:.1f}" text-anchor="end" font-size="11" fill="currentColor" '
                 f'opacity="0.75">{formatador(t)}</text>')
    passo_lbl = max(1, len(labels) // 12)
    for i, l in enumerate(labels):
        if i % passo_lbl == 0:
            p.append(f'<text x="{x(i):.1f}" y="{altura-24}" text-anchor="middle" font-size="10" '
                     f'fill="currentColor" opacity="0.75">{esc(l)}</text>')
    for nome, vs, cor in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vs) if v is not None)
        p.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" stroke-width="2.5"/>')
        for i, v in enumerate(vs):
            if v is not None:
                p.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.6" fill="{cor}"/>')
    lx = ml
    for nome, _, cor in series:
        p.append(f'<rect x="{lx}" y="{altura-13}" width="10" height="10" fill="{cor}" rx="2"/>')
        p.append(f'<text x="{lx+14}" y="{altura-4}" font-size="11" fill="currentColor">{esc(nome)}</text>')
        lx += 22 + len(nome) * 6.6
    p.append("</svg>")
    return "".join(p)


def svg_barras_empilhadas(labels, componentes, linha=None, altura=330, largura=880):
    """Barras empilhadas com positivos acima e negativos abaixo do zero.
    componentes = [(nome, [valores], cor)]. Usado na decomposicao de MRR.
    """
    ml, mr, mt, mb = 78, 16, 16, 46
    pw, ph = largura - ml - mr, altura - mt - mb
    pos = [sum(max(0, c[1][i]) for c in componentes) for i in range(len(labels))]
    neg = [sum(min(0, c[1][i]) for c in componentes) for i in range(len(labels))]
    vmax, vmin = max(pos + [0]), min(neg + [0])
    if linha:
        vmax = max(vmax, max(v for v in linha[1] if v is not None))
    ticks = _eixo_y(vmin, vmax)
    bw = pw / max(1, len(labels)) * 0.62

    def x(i):
        return ml + pw * (i + 0.5) / max(1, len(labels))

    def y(v):
        return mt + ph - (ph * (v - vmin) / ((vmax - vmin) or 1))

    p = [f'<svg viewBox="0 0 {largura} {altura}" role="img" style="width:100%;height:auto">']
    for t in ticks:
        p.append(f'<line x1="{ml}" y1="{y(t):.1f}" x2="{ml+pw}" y2="{y(t):.1f}" stroke="{CINZA}" '
                 f'stroke-opacity="0.25"/>')
        p.append(f'<text x="{ml-8}" y="{y(t)+4:.1f}" text-anchor="end" font-size="11" fill="currentColor" '
                 f'opacity="0.75">{brl(t)}</text>')
    p.append(f'<line x1="{ml}" y1="{y(0):.1f}" x2="{ml+pw}" y2="{y(0):.1f}" stroke="currentColor" '
             f'stroke-opacity="0.55" stroke-width="1.4"/>')
    for i in range(len(labels)):
        acc_p = acc_n = 0.0
        for nome, vs, cor in componentes:
            v = vs[i]
            if v is None or v == 0:
                continue
            if v > 0:
                y0, y1 = y(acc_p + v), y(acc_p)
                acc_p += v
            else:
                y0, y1 = y(acc_n), y(acc_n + v)
                acc_n += v
            p.append(f'<rect x="{x(i)-bw/2:.1f}" y="{min(y0,y1):.1f}" width="{bw:.1f}" '
                     f'height="{abs(y1-y0):.1f}" fill="{cor}" opacity="0.92"/>')
    passo_lbl = max(1, len(labels) // 12)
    for i, l in enumerate(labels):
        if i % passo_lbl == 0:
            p.append(f'<text x="{x(i):.1f}" y="{altura-24}" text-anchor="middle" font-size="10" '
                     f'fill="currentColor" opacity="0.75">{esc(l)}</text>')
    if linha:
        nome, vs, cor = linha
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vs) if v is not None)
        p.append(f'<polyline points="{pts}" fill="none" stroke="{cor}" stroke-width="2.6"/>')
    lx = ml
    leg = list(componentes) + ([linha] if linha else [])
    for nome, _, cor in leg:
        p.append(f'<rect x="{lx}" y="{altura-13}" width="10" height="10" fill="{cor}" rx="2"/>')
        p.append(f'<text x="{lx+14}" y="{altura-4}" font-size="11" fill="currentColor">{esc(nome)}</text>')
        lx += 22 + len(nome) * 6.4
    p.append("</svg>")
    return "".join(p)


def svg_waterfall(itens, altura=380, largura=880):
    """Waterfall do bridge de erro. itens = [(rotulo, valor, papel)]."""
    ml, mr, mt, mb = 92, 16, 24, 96
    pw, ph = largura - ml - mr, altura - mt - mb
    acum, niveis = 0.0, []
    for rotulo, valor, papel in itens:
        if papel == "partida":
            niveis.append((rotulo, 0, valor, papel, valor))
            acum = valor
        elif papel == "ajuste":
            niveis.append((rotulo, acum, acum + valor, papel, valor))
            acum += valor
        else:
            niveis.append((rotulo, 0, valor, papel, valor))
    vals = [v for _, a, b, _, _ in niveis for v in (a, b)]
    vmin, vmax = min(0, min(vals)), max(vals) * 1.06
    ticks = _eixo_y(vmin, vmax)
    bw = pw / len(niveis) * 0.6

    def x(i):
        return ml + pw * (i + 0.5) / len(niveis)

    def y(v):
        return mt + ph - (ph * (v - vmin) / ((vmax - vmin) or 1))

    p = [f'<svg viewBox="0 0 {largura} {altura}" role="img" style="width:100%;height:auto">']
    for t in ticks:
        p.append(f'<line x1="{ml}" y1="{y(t):.1f}" x2="{ml+pw}" y2="{y(t):.1f}" stroke="{CINZA}" stroke-opacity="0.25"/>')
        p.append(f'<text x="{ml-8}" y="{y(t)+4:.1f}" text-anchor="end" font-size="11" fill="currentColor" '
                 f'opacity="0.75">{brl(t/1000)}k</text>')
    for i, (rotulo, a, b, papel, valor) in enumerate(niveis):
        cor = AZUL if papel in ("partida", "chegada") else (VERDE if valor > 0 else VERMELHO)
        y0, y1 = y(a), y(b)
        p.append(f'<rect x="{x(i)-bw/2:.1f}" y="{min(y0,y1):.1f}" width="{bw:.1f}" '
                 f'height="{max(2.5, abs(y1-y0)):.1f}" fill="{cor}" opacity="0.92" rx="2"/>')
        p.append(f'<text x="{x(i):.1f}" y="{min(y0,y1)-6:.1f}" text-anchor="middle" font-size="10.5" '
                 f'font-weight="600" fill="currentColor">{brl(valor/1000)}k</text>')
        if papel == "ajuste" and i > 0:
            p.append(f'<line x1="{x(i-1)+bw/2:.1f}" y1="{y(a):.1f}" x2="{x(i)-bw/2:.1f}" y2="{y(a):.1f}" '
                     f'stroke="{CINZA}" stroke-dasharray="3,3" stroke-width="1"/>')
        rot = rotulo if len(rotulo) <= 22 else rotulo[:21] + "."
        p.append(f'<text transform="translate({x(i):.1f},{mt+ph+12}) rotate(38)" font-size="10" '
                 f'fill="currentColor" opacity="0.85">{esc(rot)}</text>')
    p.append("</svg>")
    return "".join(p)


def svg_dispersao(pontos, altura=340, largura=880):
    """Dispersao receita x margem por cliente. pontos = [(receita, margem, nome)]."""
    ml, mr, mt, mb = 88, 16, 20, 52
    pw, ph = largura - ml - mr, altura - mt - mb
    if not pontos:
        return "<p>sem dados</p>"
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    xmax, ymin, ymax = max(xs) * 1.05 or 1, min(0, min(ys)) * 1.1, max(ys) * 1.08 or 1

    def X(v):
        return ml + pw * v / xmax

    def Y(v):
        return mt + ph - ph * (v - ymin) / ((ymax - ymin) or 1)

    p = [f'<svg viewBox="0 0 {largura} {altura}" role="img" style="width:100%;height:auto">']
    for t in _eixo_y(ymin, ymax):
        p.append(f'<line x1="{ml}" y1="{Y(t):.1f}" x2="{ml+pw}" y2="{Y(t):.1f}" stroke="{CINZA}" stroke-opacity="0.22"/>')
        p.append(f'<text x="{ml-8}" y="{Y(t)+4:.1f}" text-anchor="end" font-size="10.5" fill="currentColor" '
                 f'opacity="0.75">{brl(t/1000)}k</text>')
    p.append(f'<line x1="{ml}" y1="{Y(0):.1f}" x2="{ml+pw}" y2="{Y(0):.1f}" stroke="{VERMELHO}" '
             f'stroke-width="1.5" stroke-dasharray="5,3"/>')
    p.append(f'<text x="{ml+pw}" y="{Y(0)-6:.1f}" text-anchor="end" font-size="10.5" fill="{VERMELHO}">'
             f'margem zero</text>')
    for i in range(6):
        v = xmax * i / 5
        p.append(f'<text x="{X(v):.1f}" y="{altura-28}" text-anchor="middle" font-size="10.5" '
                 f'fill="currentColor" opacity="0.75">{brl(v/1000)}k</text>')
    for rec, mrg, nome in pontos:
        cor = VERMELHO if mrg < 0 else VERDE
        p.append(f'<circle cx="{X(rec):.1f}" cy="{Y(mrg):.1f}" r="4.2" fill="{cor}" opacity="0.72"/>')
    p.append(f'<text x="{ml+pw/2:.1f}" y="{altura-8}" text-anchor="middle" font-size="11" fill="currentColor" '
             f'opacity="0.85">receita reconhecida no periodo (BRL)</text>')
    p.append("</svg>")
    return "".join(p)


def tabela(cols, linhas, alinhar_dir=None, destaque=None):
    ad = alinhar_dir or set()
    out = ['<div class="table-wrap"><table><thead><tr>']
    for i, c in enumerate(cols):
        out.append(f'<th{" class=dir" if i in ad else ""}>{esc(c)}</th>')
    out.append("</tr></thead><tbody>")
    for n, linha in enumerate(linhas):
        cls = ' class="neg"' if destaque and destaque(n, linha) else ""
        out.append(f"<tr{cls}>")
        for i, v in enumerate(linha):
            out.append(f'<td{" class=dir" if i in ad else ""}>{v if isinstance(v, str) else esc(v)}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)
