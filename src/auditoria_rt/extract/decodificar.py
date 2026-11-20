"""Normaliza o conteúdo da coluna de XML vindo do SAP para bytes UTF-8."""

from __future__ import annotations

import base64
import binascii
import gzip
import zlib


def _ler_lob(valor):
    # hdbcli devolve LOBs com .read(); pyodbc devolve str/bytes
    if hasattr(valor, "read"):
        valor = valor.read()
    if isinstance(valor, memoryview):
        valor = valor.tobytes()
    return valor


def decodificar(valor, modo: str = "auto") -> bytes:
    valor = _ler_lob(valor)
    if valor is None:
        raise ValueError("XML nulo")
    if isinstance(valor, str):
        bruto = valor.encode("utf-8")
    else:
        bruto = bytes(valor)

    if modo == "texto":
        return bruto
    if modo == "base64":
        return decodificar(base64.b64decode(bruto), "auto")
    if modo == "gzip":
        return gzip.decompress(bruto)
    if modo == "zlib":
        return zlib.decompress(bruto)
    if modo != "auto":
        raise ValueError(f"codificacao_xml desconhecida: {modo}")

    # auto: detecta pelo conteúdo
    if bruto[:3] == b"\xef\xbb\xbf":
        bruto = bruto[3:]
    inicio = bruto.lstrip()[:5]
    if inicio.startswith(b"<"):
        return bruto
    if bruto[:2] == b"\x1f\x8b":
        return gzip.decompress(bruto)
    if bruto[:1] == b"\x78":
        try:
            return zlib.decompress(bruto)
        except zlib.error:
            pass
    if bruto[:3] == b"\xef\xbb\xbf":
        return bruto[3:]
    try:
        dec = base64.b64decode(b"".join(bruto.split()), validate=True)
        if dec:
            return decodificar(dec, "auto")
    except (binascii.Error, ValueError):
        pass
    # SAP às vezes grava XML como HEX (RAWSTRING exportado)
    try:
        return decodificar(bytes.fromhex(bruto.decode("ascii")), "auto")
    except (ValueError, UnicodeDecodeError):
        pass
    raise ValueError("Não foi possível identificar a codificação do XML")
