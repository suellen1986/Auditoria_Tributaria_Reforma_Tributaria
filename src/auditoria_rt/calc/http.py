"""Cliente da calculadora publicada internamente (HTTP local, sem internet)."""

from __future__ import annotations

import logging
import threading
import time

import requests

from auditoria_rt.calc import contrato
from auditoria_rt.calc.base import Calculadora, ParametroCalculo, ResultadoCalculo

log = logging.getLogger(__name__)


class CalculadoraHTTP(Calculadora):
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.url = cfg["url_base"].rstrip("/") + cfg["endpoint_calculo"]
        self.timeout = float(cfg.get("timeout_s", 60))
        self.tentativas = int(cfg.get("tentativas", 3))
        self.verificar_tls = cfg.get("verificar_tls", True)
        self.cabecalhos = {"Content-Type": "application/json", **(cfg.get("cabecalhos") or {})}
        self.versao = str(cfg.get("versao") or "nao-informada")
        self._local = threading.local()

    def _sessao(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update(self.cabecalhos)
            # chamadas internas: não usar proxy corporativo para a calculadora local
            s.trust_env = bool(self.cfg.get("usar_proxy_ambiente", False))
            self._local.s = s
        return s

    def calcular(self, params: list[ParametroCalculo]) -> list[ResultadoCalculo]:
        corpo = contrato.montar_requisicao(params, self.cfg)
        ultimo_erro = ""
        for tentativa in range(1, self.tentativas + 1):
            try:
                r = self._sessao().post(self.url, json=corpo, timeout=self.timeout, verify=self.verificar_tls)
            except requests.RequestException as e:
                ultimo_erro = f"Falha de comunicação: {e}"
                time.sleep(min(2 ** tentativa, 30))
                continue
            if r.status_code >= 500 or r.status_code == 429:
                ultimo_erro = contrato.ler_erro(r.status_code, r.text)
                time.sleep(min(2 ** tentativa, 30))
                continue
            if r.status_code >= 400:
                # Erro de negócio (combinação rejeitada): não adianta repetir.
                # Se o lote tiver vários itens, recalcula um a um para isolar o item rejeitado.
                if len(params) > 1:
                    out = []
                    for p in params:
                        out.extend(self.calcular([p]))
                    return out
                msg = contrato.ler_erro(r.status_code, r.text)
                return [ResultadoCalculo(ref=p.ref, status="ERRO", mensagem=msg) for p in params]
            return contrato.ler_resposta(r.json(), params)
        log.warning("Calculadora indisponível após %d tentativas: %s", self.tentativas, ultimo_erro)
        return [ResultadoCalculo(ref=p.ref, status="FALHA", mensagem=ultimo_erro) for p in params]

    def testar(self) -> str:
        endpoint = self.cfg.get("endpoint_versao")
        if endpoint:
            r = self._sessao().get(self.cfg["url_base"].rstrip("/") + endpoint, timeout=self.timeout,
                                   verify=self.verificar_tls)
            return f"HTTP {r.status_code}: {r.text[:200]}"
        import datetime as dt
        p = ParametroCalculo(dt.date.today(), "RJ", "3304557", "27101259", "000", "000001", ref="teste")
        res = self.calcular([p])[0]
        return f"{res.status}: {res.mensagem or 'resposta recebida'}"
