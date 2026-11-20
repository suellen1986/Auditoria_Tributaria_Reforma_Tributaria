"""Linha de comando.

Exemplos:
  auditoria-rt -c config/config.yaml testar-conexoes
  auditoria-rt -c config/config.yaml executar --de 2026-01-01 --ate 2026-01-31
  auditoria-rt -c config/config.yaml extrair --de 2026-01-01 --ate 2026-01-31
  auditoria-rt -c config/config.yaml processar
  auditoria-rt -c config/config.yaml calcular --de 2026-01-01 --ate 2026-01-31
  auditoria-rt -c config/config.yaml auditar --de 2026-01-01 --ate 2026-01-31
  auditoria-rt -c config/config.yaml catalogo
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys

from auditoria_rt import config as config_mod
from auditoria_rt import log as log_mod
from auditoria_rt import pipeline
from auditoria_rt.workspace import Workspace

log = logging.getLogger("auditoria_rt")


def _data(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _periodo(p: argparse.ArgumentParser, obrigatorio: bool) -> None:
    p.add_argument("--de", type=_data, required=obrigatorio, help="data inicial (AAAA-MM-DD)")
    p.add_argument("--ate", type=_data, required=obrigatorio, help="data final (AAAA-MM-DD), inclusive")


def construir_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="auditoria-rt", description="Auditoria em lote de NF-e - IBS/CBS/IS")
    ap.add_argument("-c", "--config", default="config/config.yaml", help="arquivo de configuração YAML")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="comando", required=True)

    sub.add_parser("testar-conexoes", help="testa SAP e calculadora")
    sub.add_parser("referencias", help="carrega as tabelas de referência (cClassTrib, alíquotas, matriz)")
    sub.add_parser("catalogo", help="lista as regras")

    p = sub.add_parser("extrair", help="extrai XMLs do SAP para parquet (por dia, retomável)")
    _periodo(p, True)
    p.add_argument("--refazer", action="store_true", help="reextrai partições já concluídas")

    p = sub.add_parser("processar", help="lê os XMLs extraídos e gera notas/itens normalizados")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--refazer", action="store_true")

    p = sub.add_parser("calcular", help="consulta a calculadora (combinações distintas + amostra)")
    _periodo(p, False)
    p.add_argument("--sem-amostra", action="store_true")
    p.add_argument("--execucao", default=None, help="identificador da execução (para a amostra)")

    p = sub.add_parser("auditar", help="executa as regras e gera o relatório")
    _periodo(p, False)
    p.add_argument("--regras", nargs="*", help="executa só estas regras (ex.: R009 C001)")
    p.add_argument("--execucao", default=None)
    p.add_argument("--sem-relatorio", action="store_true")

    p = sub.add_parser("executar", help="processo completo: referências, extração, parse, cálculo, regras, relatório")
    _periodo(p, True)
    p.add_argument("--sem-extracao", action="store_true", help="usa os dados já extraídos")
    p.add_argument("--workers", type=int, default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.comando == "catalogo":
        from auditoria_rt.rules.base import todas
        for r in todas():
            print(f"{r.id:5} {r.severidade:6} {r.bloco:11} {r.titulo}")
        return 0
    try:
        cfg = config_mod.carregar(args.config)
    except FileNotFoundError:
        print(f"Configuração não encontrada: {args.config}\n"
              f"Copie config/config.exemplo.yaml para config/config.yaml e ajuste.", file=sys.stderr)
        return 2
    except KeyError as e:
        print(f"Erro na configuração: {e}", file=sys.stderr)
        return 2
    ws = Workspace(cfg)
    log_mod.configurar(ws.dir / "logs", logging.DEBUG if args.verbose else logging.INFO)
    try:
        return _despachar(args, ws)
    finally:
        ws.fechar()


def _imprimir(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _despachar(args, ws: Workspace) -> int:
    cmd = args.comando
    if cmd == "catalogo":
        from auditoria_rt.rules.base import todas
        for r in todas():
            print(f"{r.id:5} {r.severidade:6} {r.bloco:11} {r.titulo}")
        return 0
    if cmd == "referencias":
        _imprimir(pipeline.etapa_referencias(ws))
        return 0
    if cmd == "testar-conexoes":
        return _testar(ws)
    if cmd == "extrair":
        _imprimir(pipeline.etapa_extrair(ws, args.de, args.ate, args.refazer))
        return 0
    if cmd == "processar":
        _imprimir(pipeline.etapa_processar(ws, args.workers, args.refazer))
        return 0
    if cmd == "calcular":
        ex = args.execucao or pipeline.nova_execucao()
        _imprimir({"execucao": ex, **pipeline.etapa_calcular(ws, ex, args.de, args.ate, not args.sem_amostra)})
        return 0
    if cmd == "auditar":
        ex = args.execucao or pipeline.nova_execucao()
        res = pipeline.etapa_auditar(ws, ex, args.de, args.ate, args.regras)
        saida = {"execucao": ex, "regras": res}
        if not args.sem_relatorio:
            saida["relatorio"] = str(pipeline.etapa_relatorio(ws, ex, args.de, args.ate))
        _imprimir(saida)
        return 0
    if cmd == "executar":
        _imprimir(pipeline.executar_tudo(ws, args.de, args.ate, not args.sem_extracao, args.workers))
        return 0
    return 2


def _testar(ws: Workspace) -> int:
    from auditoria_rt.calc.orquestrador import criar_calculadora
    from auditoria_rt.extract import criar_fonte

    ok = True
    for f in ws.cfg["extracao"].get("fontes", []):
        try:
            print(f"[fonte {f.get('nome')}] {criar_fonte(f, ws.cfg['extracao']).testar()}")
        except Exception as e:
            ok = False
            print(f"[fonte {f.get('nome')}] FALHA: {type(e).__name__}: {e}")
    try:
        ws.carregar_referencias()
        msg = criar_calculadora(ws).testar()
        print(f"[calculadora] {msg}")
        if msg.startswith(("FALHA", "ERRO")):
            ok = False
    except Exception as e:
        ok = False
        print(f"[calculadora] FALHA: {type(e).__name__}: {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
