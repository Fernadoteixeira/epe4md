from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
PACKAGED_DATA_DIRECTORY = Path(__file__).resolve().parent / "dados_premissas"
REPOSITORY_DATA_DIRECTORY = PACKAGE_ROOT / "inst" / "dados_premissas"


def premise_directory(ano_base: int, directory: str | Path | None = None) -> Path:
    """Resolve and validate the directory containing premise workbooks."""
    if directory:
        selected = Path(directory)
    else:
        selected = PACKAGED_DATA_DIRECTORY / str(ano_base)
        if not selected.is_dir():
            selected = REPOSITORY_DATA_DIRECTORY / str(ano_base)
    if not selected.is_dir():
        raise ValueError(
            f"Diretório de premissas não encontrado: {selected}. "
            "Informe dir_dados_premissas com os arquivos XLSX da versão do ano-base."
        )
    return selected


def load_workbook(ano_base: int, filename: str, directory: str | Path | None = None,
                  sheet_name: str | int = 0) -> pd.DataFrame:
    """Load one source workbook with a Portuguese, actionable validation error."""
    path = premise_directory(ano_base, directory) / filename
    if not path.is_file():
        raise ValueError(f"Arquivo de premissas obrigatório não encontrado: {path}")
    return pd.read_excel(path, sheet_name=sheet_name)


def records_to_dataframe(records: object, parameter_name: str) -> pd.DataFrame:
    if isinstance(records, pd.DataFrame):
        return records.copy()
    if isinstance(records, list) and all(isinstance(record, dict) for record in records):
        return pd.DataFrame.from_records(records)
    raise TypeError(f"{parameter_name} deve ser um pandas.DataFrame ou uma lista de objetos.")


def require_columns(dataframe: pd.DataFrame, columns: list[str], parameter_name: str) -> None:
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ValueError(f"{parameter_name} não possui as colunas obrigatórias: {', '.join(missing)}.")


def result_records(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        clean = value.astype(object).where(pd.notna(value), None)
        return clean.to_dict(orient="records")
    if isinstance(value, dict):
        return {key: result_records(item) for key, item in value.items()}
    return value
