"""Column-name normalization for cross-dataset joins.

Colombian open-data datasets repeat the same concept under many spellings
(nit_entidad, nit_de_la_entidad, cod_dane, codigodane, municipio_id, ...).
We canonicalize them so the graph builder can propose JOINABLE_ON edges.
"""
from __future__ import annotations

import re
import unicodedata

# Map from any (lowercased, accent-stripped) column name to a canonical concept.
COLUMN_SYNONYMS: dict[str, str] = {
    # NIT — national company id
    "nit_entidad": "nit",
    "nit_de_la_entidad": "nit",
    "nit": "nit",
    "nitproveedor": "nit",
    "nit_proveedor": "nit",
    "nitentidad": "nit",
    # DANE municipal code
    "cod_dane": "codigo_dane",
    "codigodane": "codigo_dane",
    "codigo_dane": "codigo_dane",
    "codigo_dane_municipio": "codigo_dane",
    "cod_municipio": "codigo_dane",
    "codigodanemunicipio": "codigo_dane",
    "dane": "codigo_dane",
    # Municipio name
    "municipio_id": "municipio",
    "nombre_municipio": "municipio",
    "municipio_contrato": "municipio",
    "municipio": "municipio",
    "ciudad": "municipio",
    "nombre_del_municipio": "municipio",
    "municipionombre": "municipio",
    # Departamento
    "departamento": "departamento",
    "codigo_departamento": "departamento",
    "cod_departamento": "departamento",
    "nombre_departamento": "departamento",
    "depto": "departamento",
    # Time
    "fecha": "fecha",
    "fecha_firma": "fecha",
    "fecha_diagnostico": "fecha",
    "vigenciadesde": "fecha",
    # Entity
    "nombre_entidad": "nombre_entidad",
    "entidad": "nombre_entidad",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_column(name: str) -> str:
    """Lowercase, strip accents, collapse non-alphanumerics to underscores, then
    apply the COLUMN_SYNONYMS map. Falls back to the cleaned name itself.
    """
    if not name:
        return ""
    s = _strip_accents(name.strip().lower())
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return COLUMN_SYNONYMS.get(s, s)
