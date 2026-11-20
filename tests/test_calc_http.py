"""CalculadoraHTTP contra um servidor falso que imita o contrato (sem rede externa)."""

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from auditoria_rt.calc.base import ParametroCalculo
from auditoria_rt.calc.http import CalculadoraHTTP


class _Fake(BaseHTTPRequestHandler):
    chamadas = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        _Fake.chamadas += 1
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if any(i["cClassTrib"] == "999999" for i in corpo["itens"]):
            self.send_response(422)
            self.end_headers()
            self.wfile.write(json.dumps({"mensagem": "cClassTrib inexistente"}).encode())
            return
        objetos = [{"nObj": i["numero"], "tribCalc": {"IBSCBS": {"gIBSCBS": {
            "gIBSUF": {"pIBSUF": 0.1, "vIBSUF": round(i["baseCalculo"] * 0.001, 2)},
            "gIBSMun": {"pIBSMun": 0.0, "vIBSMun": 0.0},
            "gCBS": {"pCBS": 0.9, "vCBS": round(i["baseCalculo"] * 0.009, 2)}}}}} for i in corpo["itens"]]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"objetos": objetos}).encode())


@pytest.fixture
def servidor():
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_http_ok_e_isolamento_de_rejeitado(servidor):
    calc = CalculadoraHTTP({"url_base": servidor, "endpoint_calculo": "/calc", "tentativas": 1, "versao": "t"})
    d = dt.date(2026, 3, 1)
    params = [ParametroCalculo(d, "SP", "3550308", "27101921", "000", "000001", base=1000, ref=1),
              ParametroCalculo(d, "SP", "3550308", "27101921", "000", "999999", base=1000, ref=2)]
    r = {x.ref: x for x in calc.calcular(params)}
    assert r[1].status == "OK" and r[1].v_cbs == 9.0 and r[1].v_ibs_uf == 1.0
    assert r[2].status == "ERRO" and "inexistente" in r[2].mensagem


def test_http_indisponivel():
    calc = CalculadoraHTTP({"url_base": "http://127.0.0.1:9", "endpoint_calculo": "/x", "tentativas": 1,
                            "timeout_s": 1})
    r = calc.calcular([ParametroCalculo(dt.date(2026, 3, 1), "SP", "1", "1", "000", "000001", ref=1)])
    assert r[0].status == "FALHA"
