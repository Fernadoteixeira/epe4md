import io
import json
import sys

import pytest

from epe4md.charts import epe4md_graf_geracao_ano
from epe4md.cli import main
from epe4md.data import records_to_dataframe


def test_chart_returns_serializable_specification():
    dados = [
        {"ano": 2021, "mes": 1, "energia_mwh": 8760},
        {"ano": 2021, "mes": 2, "energia_mwh": 6720},
    ]

    specification = epe4md_graf_geracao_ano(dados, ano_inicio=2021)

    assert specification["tipo"] == "area"
    assert specification["eixo_x"] == "ano"
    assert specification["dados"][0]["energia_mwmed"] == pytest.approx(
        (8760 + 6720) / (24 * (31 + 28))
    )


def test_records_to_dataframe_rejects_unsupported_input():
    with pytest.raises(TypeError, match="dados"):
        records_to_dataframe("not tabular", "dados")


def test_cli_serializes_public_workflow_result(monkeypatch, capsys):
    request = {
        "function": "epe4md_sumariza_resultados",
        "arguments": {
            "resultados_mensais": [
                {"ano": 2021, "pot_mes_mw": 1000, "energia_mwh": 8760}
            ]
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))

    main()

    result = json.loads(capsys.readouterr().out)
    assert result == [
        {"ano": 2021, "pot_ano": 1.0, "geracao_gwh": 8.76,
         "pot_acum": 1.0, "geracao_mwmed": 1.0}
    ]


def test_cli_rejects_unknown_function(monkeypatch):
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"function": "unknown", "arguments": {}})),
    )
