import gzip
import base64

import pytest

from auditoria_rt.extract.decodificar import decodificar
from auditoria_rt.parse.nfe import ErroParse, parse_nfe
from auditoria_rt.sintetico import ItemSint, NotaSint, chave_sintetica, gerar_xml


def test_parse_basico():
    nota = NotaSint(chave=chave_sintetica(1), itens=[ItemSint(v_prod=1000), ItemSint(v_prod=500, ncm="27101259")])
    cab, itens = parse_nfe(gerar_xml(nota))
    assert cab["chave"] == nota.chave
    assert cab["qtd_itens"] == 2
    assert cab["tot_presente"] is True
    assert cab["tot_v_cbs"] == pytest.approx(13.5)
    i1 = itens[0]
    assert i1["cst"] == "000" and i1["cclasstrib"] == "000001"
    assert i1["v_bc"] == 1000 and i1["p_cbs"] == 0.9 and i1["v_cbs"] == 9.0
    assert i1["p_ibs_uf"] == 0.1 and i1["v_ibs_uf"] == 1.0
    assert i1["uf_dest"] == "SP" and i1["c_mun_dest"] == "3550308"
    assert itens[1]["ncm"] == "27101259"


def test_parse_sem_namespace_e_grupos():
    it = ItemSint(cst="200", cclasstrib="200001", p_red=60)
    nota = NotaSint(chave=chave_sintetica(2), itens=[it], namespace=False)
    _, itens = parse_nfe(gerar_xml(nota))
    i = itens[0]
    assert i["tem_g_red"] and not i["tem_g_dif"]
    assert i["p_red_aliq_cbs"] == 60 and i["p_aliq_efet_cbs"] == pytest.approx(0.36)
    assert i["v_cbs"] == pytest.approx(3.6)


def test_parse_monofasico():
    it = ItemSint(cst="620", cclasstrib="620001", mono={"q": 1000, "ad_rem_ibs": 0.1, "ad_rem_cbs": 0.2})
    _, itens = parse_nfe(gerar_xml(NotaSint(chave=chave_sintetica(3), itens=[it])))
    i = itens[0]
    assert i["tem_mono"] and i["q_bc_mono"] == 1000 and i["v_cbs_mono"] == 200


def test_parse_item_sem_ibscbs():
    _, itens = parse_nfe(gerar_xml(NotaSint(chave=chave_sintetica(4), itens=[ItemSint(sem_ibscbs=True)])))
    assert itens[0]["ibscbs_presente"] is False


def test_parse_invalido():
    with pytest.raises(ErroParse):
        parse_nfe(b"<nfeProc><NFe>")
    with pytest.raises(ErroParse):
        parse_nfe(b"<outro/>")


def test_parse_rejeita_entidades_externas():
    xml = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><infNFe Id="NFe1">&e;</infNFe>'
    cab, _ = parse_nfe(xml)
    assert "root" not in str(cab)


@pytest.mark.parametrize("modo", ["texto", "gzip", "base64", "hex"])
def test_decodificar(modo):
    xml = gerar_xml(NotaSint(chave=chave_sintetica(5))).encode()
    bruto = {"texto": xml, "gzip": gzip.compress(xml), "base64": base64.b64encode(xml),
             "hex": xml.hex().upper().encode()}[modo]
    assert decodificar(bruto, "auto") == xml
