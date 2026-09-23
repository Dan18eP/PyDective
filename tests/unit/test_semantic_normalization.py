import pytest
from app.domain.errors import ParametrosVaciosError
from app.services.semantic_extraction_service import (
    normalize_parameter,
    canonicalize_parameters,
    expand_parameter_synonyms,
)


def test_normalize_parameter_accents_and_case():
    assert normalize_parameter("Facturación") == "facturacion"
    assert normalize_parameter("NÚMERO DE RADICADO") == "numero de radicado"
    assert normalize_parameter("  Año Fiscal  ") == "ano fiscal"


def test_normalize_parameter_ligatures():
    # Ligatures ﬁ (\ufb01) and ﬂ (\ufb02)
    assert normalize_parameter("ﬁnanzas") == "finanzas"
    assert normalize_parameter("ﬂujo de caja") == "flujo de caja"


def test_normalize_parameter_punctuation_and_spaces():
    assert normalize_parameter("Total: ") == "total"
    assert normalize_parameter("  Subtotal  -  neto  ") == "subtotal - neto"


def test_canonicalize_parameters_comma_separated_nfkd():
    # US-02 Escenario 1: "  Facturación, TOTAL, número de radicado  "
    raw_input = "  Facturación, TOTAL, número de radicado  "
    canonical_list, query_hash = canonicalize_parameters(raw_input)

    assert canonical_list == ["facturacion", "numero de radicado", "total"]
    assert len(query_hash) == 16
    assert isinstance(query_hash, str)


def test_canonicalize_parameters_deduplication_and_order_identity():
    # US-02 Escenario 2: ["total", "fecha"] vs ["FECHA", "total", "  total  "]
    input_a = ["total", "fecha"]
    input_b = ["FECHA", "total", "  total  "]

    list_a, hash_a = canonicalize_parameters(input_a)
    list_b, hash_b = canonicalize_parameters(input_b)

    assert list_a == ["fecha", "total"]
    assert list_b == ["fecha", "total"]
    assert hash_a == hash_b, "Identical parameter sets in any order/casing must yield identical L0 query_hash"


def test_canonicalize_parameters_json_string():
    json_str = '["TOTAL", "subtotal", "IVA"]'
    canonical_list, query_hash = canonicalize_parameters(json_str)

    assert canonical_list == ["iva", "subtotal", "total"]
    assert query_hash


def test_canonicalize_parameters_rejects_empty_string():
    # US-03 Escenario 2: parametros=""
    with pytest.raises(ParametrosVaciosError) as exc_info:
        canonicalize_parameters("")
    assert exc_info.value.code == "EMPTY_SEARCH_PARAMETERS"


def test_canonicalize_parameters_rejects_only_commas_and_spaces():
    # US-03 Escenario 2: parametros="  , ,  "
    with pytest.raises(ParametrosVaciosError) as exc_info:
        canonicalize_parameters("  , ,  ")
    assert exc_info.value.code == "EMPTY_SEARCH_PARAMETERS"


def test_canonicalize_parameters_rejects_empty_list():
    with pytest.raises(ParametrosVaciosError) as exc_info:
        canonicalize_parameters([])
    assert exc_info.value.code == "EMPTY_SEARCH_PARAMETERS"


def test_canonicalize_parameters_rejects_list_with_only_empty_strings():
    with pytest.raises(ParametrosVaciosError) as exc_info:
        canonicalize_parameters(["  ", ""])
    assert exc_info.value.code == "EMPTY_SEARCH_PARAMETERS"


def test_expand_parameter_synonyms_known_term():
    synonyms = expand_parameter_synonyms("total")
    assert "total" in synonyms
    assert "valor total" in synonyms
    assert "importe total" in synonyms


def test_expand_parameter_synonyms_accented_term():
    synonyms = expand_parameter_synonyms("Facturación")
    assert "factura" in synonyms or "facturacion" in synonyms


def test_expand_parameter_synonyms_arbitrary_term_is_document_agnostic():
    # Arbitrary custom field not in standard dictionary
    custom_field = "numero de contenedor martimo"
    synonyms = expand_parameter_synonyms(custom_field)
    assert synonyms == ["numero de contenedor martimo"]
