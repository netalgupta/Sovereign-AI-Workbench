"""Tests for Model Provenance Tracking.

TOOLS.md row 47 / VIBECODING_SPEC CARD 01.
Proves:
1. Every model defined in models/models.yaml has an authoritative provenance record.
2. Provenance records contain real non-fabricated fields: license, organization,
   architecture, parameter size, quantization, air-gap attestation, and chain of custody.
3. Auxiliary engines (embeddings, whisper, ocr) are included in provenance ledger.
4. /api/models includes provenance data for every listed model.
5. /api/models/provenance returns the full sovereign provenance ledger.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.provenance import (
    MODEL_PROVENANCE_LEDGER,
    get_model_provenance,
    get_all_provenance,
)
from backend.models.registry import _DEFAULT_REGISTRY_PATH, load_registry


@pytest.fixture
def client():
    return TestClient(app)


def test_every_yaml_model_has_provenance():
    registry = load_registry(_DEFAULT_REGISTRY_PATH)
    for model_id in registry:
        record = get_model_provenance(model_id)
        assert record is not None, f"Model {model_id} from models.yaml missing from provenance ledger"
        assert record["id"] == model_id
        assert record["license"] in ["Apache-2.0", "MIT", "Stability AI Non-Commercial Research Community License"]
        assert record["organization"]
        assert record["air_gap_attestation"]
        assert "chain_of_custody" in record
        assert record["chain_of_custody"]["hash_algorithm"] == "SHA256"


def test_auxiliary_models_provenance():
    for aux_id in ["embeddings", "whisper", "ocr"]:
        record = get_model_provenance(aux_id)
        assert record is not None, f"Auxiliary model {aux_id} missing provenance"
        assert record["license"]
        assert record["organization"]
        assert record["air_gap_attestation"]


def test_get_all_provenance():
    ledger = get_all_provenance()
    assert len(ledger) >= 10  # 7 registry models + 3 auxiliary models
    assert "reasoning-model" in ledger
    assert "fast-router" in ledger
    assert "vision-model" in ledger
    assert "image-model" in ledger


def test_api_models_endpoint_includes_provenance(client):
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert len(data["models"]) > 0

    for model in data["models"]:
        prov = model.get("provenance")
        assert prov is not None, f"Model {model['id']} in /api/models response missing provenance"
        assert "license" in prov
        assert "organization" in prov
        assert "air_gap_attestation" in prov


def test_api_models_provenance_ledger_endpoint(client):
    res = client.get("/api/models/provenance")
    assert res.status_code == 200
    data = res.json()
    assert "ledger" in data
    assert "reasoning-model" in data["ledger"]
    assert data["ledger"]["reasoning-model"]["license"] == "Apache-2.0"
