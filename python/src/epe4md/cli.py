from __future__ import annotations
import json
import sys
from typing import Any
import numpy as np
import pandas as pd
import epe4md
from .data import result_records

def _json_default(value: object) -> object:
    if isinstance(value, (np.integer, np.floating)): return value.item()
    if isinstance(value, (pd.Timestamp, pd.Timedelta)): return str(value)
    raise TypeError(f"Valor não serializável na resposta: {type(value).__name__}")

def main() -> None:
    request = json.load(sys.stdin)
    function_name = request.get("function")
    arguments = request.get("arguments", {})
    if not isinstance(function_name, str) or not function_name.startswith("epe4md_"):
        raise ValueError("function deve identificar uma função pública epe4md_.")
    if not isinstance(arguments, dict): raise TypeError("arguments deve ser um objeto JSON.")
    function = getattr(epe4md, function_name, None)
    if function is None: raise ValueError(f"Função pública desconhecida: {function_name}.")
    print(json.dumps(result_records(function(**arguments)), ensure_ascii=False, allow_nan=False, default=_json_default))
if __name__ == "__main__": main()
