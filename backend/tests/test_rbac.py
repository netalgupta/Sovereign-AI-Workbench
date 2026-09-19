"""Tests for Role-Based Access Control (RBAC) on Knowledge Base & Retrieval.

TOOLS.md row 46 / FRONTEND.md §3.11 / SYSTEM.md line 126.
Proves:
1. Manifest returns 4 role tiers and 6 categories matching FRONTEND §3.11.
2. Category resolution maps corpus directory paths to proper category IDs.
3. HSE Specialist cannot access 04_SAP_Mock_Exports and 05_Correspondence.
4. Plant Engineer cannot access 05_Correspondence, but can access 01-04 and 06.
5. Superintendent / Approver and Admin have full access to all categories.
6. /api/rbac/tiers endpoint returns the authoritative matrix.
7. /api/corpus?role=... filters visible tree, directories, and sources.
8. /api/search with role prunes unauthorized chunks and provides explicit refusal
   when all retrieved chunks fall into restricted categories.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.auth.rbac import (
    RBAC_TIERS,
    RBAC_CATEGORIES,
    normalize_role,
    get_category_for_path,
    is_category_allowed,
    is_path_allowed,
    filter_chunks_by_role,
    filter_corpus_tree,
    get_rbac_manifest,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_rbac_manifest_structure():
    manifest = get_rbac_manifest()
    assert "tiers" in manifest
    assert "categories" in manifest
    assert len(manifest["tiers"]) == 4
    assert len(manifest["categories"]) == 6

    category_ids = {c["id"] for c in manifest["categories"]}
    expected_categories = {"sops", "inspection", "quality", "sap_mock", "correspondence", "diagrams"}
    assert category_ids == expected_categories

    role_ids = {t["role_id"] for t in manifest["tiers"]}
    expected_roles = {"plant_engineer", "hse_specialist", "superintendent", "system_admin"}
    assert role_ids == expected_roles


def test_role_normalization():
    assert normalize_role("Plant Engineer") == "plant_engineer"
    assert normalize_role("plant_engineer") == "plant_engineer"
    assert normalize_role("engineer") == "plant_engineer"
    assert normalize_role("operations") == "plant_engineer"

    assert normalize_role("HSE Specialist") == "hse_specialist"
    assert normalize_role("hse") == "hse_specialist"
    assert normalize_role("safety") == "hse_specialist"

    assert normalize_role("Superintendent / Approver") == "superintendent"
    assert normalize_role("approver") == "superintendent"
    assert normalize_role("superintendent") == "superintendent"

    assert normalize_role("System Administrator") == "system_admin"
    assert normalize_role("admin") == "system_admin"


def test_get_category_for_path():
    assert get_category_for_path("MRPL_RAG_Test_Corpus/01_SOPs_and_Procedures/SOP_HCU2.md") == "sops"
    assert get_category_for_path("02_Inspection_and_Maintenance\\Report_CCR1.pdf") == "inspection"
    assert get_category_for_path("MRPL_RAG_Test_Corpus/03_Quality_and_Process_Data/QA.xlsx") == "quality"
    assert get_category_for_path("04_SAP_Mock_Exports/MM_Materials.csv") == "sap_mock"
    assert get_category_for_path("05_Correspondence/Kasargod_Depot.txt") == "correspondence"
    assert get_category_for_path("06_Diagrams_and_Scans/PID_Schematic.png") == "diagrams"
    assert get_category_for_path("07_User_Uploads/my_notes.txt") is None


def test_hse_specialist_permissions():
    role = "hse_specialist"
    # Permitted
    assert is_category_allowed(role, "sops") is True
    assert is_category_allowed(role, "inspection") is True
    assert is_category_allowed(role, "quality") is True
    assert is_category_allowed(role, "diagrams") is True
    # Denied
    assert is_category_allowed(role, "sap_mock") is False
    assert is_category_allowed(role, "correspondence") is False

    assert is_path_allowed(role, "MRPL_RAG_Test_Corpus/01_SOPs_and_Procedures/sop.md") is True
    assert is_path_allowed(role, "MRPL_RAG_Test_Corpus/04_SAP_Mock_Exports/sap.csv") is False
    assert is_path_allowed(role, "MRPL_RAG_Test_Corpus/05_Correspondence/letter.txt") is False


def test_plant_engineer_permissions():
    role = "plant_engineer"
    # Permitted
    assert is_category_allowed(role, "sops") is True
    assert is_category_allowed(role, "inspection") is True
    assert is_category_allowed(role, "quality") is True
    assert is_category_allowed(role, "sap_mock") is True
    assert is_category_allowed(role, "diagrams") is True
    # Denied
    assert is_category_allowed(role, "correspondence") is False

    assert is_path_allowed(role, "MRPL_RAG_Test_Corpus/04_SAP_Mock_Exports/sap.csv") is True
    assert is_path_allowed(role, "MRPL_RAG_Test_Corpus/05_Correspondence/letter.txt") is False


def test_superintendent_and_admin_full_access():
    for role in ["superintendent", "system_admin"]:
        for cat in ["sops", "inspection", "quality", "sap_mock", "correspondence", "diagrams"]:
            assert is_category_allowed(role, cat) is True


def test_filter_chunks_by_role():
    chunks = [
        {"source_document": "01_SOPs_and_Procedures/sop.md", "text": "HCU shutdown step"},
        {"source_document": "04_SAP_Mock_Exports/materials.csv", "text": "PO 450001234"},
        {"source_document": "05_Correspondence/depot_memo.txt", "text": "Dispatch to Kasargod"},
    ]

    hse_chunks = filter_chunks_by_role("hse_specialist", chunks)
    assert len(hse_chunks) == 1
    assert hse_chunks[0]["source_document"] == "01_SOPs_and_Procedures/sop.md"

    eng_chunks = filter_chunks_by_role("plant_engineer", chunks)
    assert len(eng_chunks) == 2
    assert {c["source_document"] for c in eng_chunks} == {
        "01_SOPs_and_Procedures/sop.md",
        "04_SAP_Mock_Exports/materials.csv",
    }

    admin_chunks = filter_chunks_by_role("system_admin", chunks)
    assert len(admin_chunks) == 3


def test_api_rbac_tiers_endpoint(client):
    res = client.get("/api/rbac/tiers")
    assert res.status_code == 200
    data = res.json()
    assert "tiers" in data
    assert "categories" in data
    assert len(data["tiers"]) == 4


def test_api_corpus_with_role_filtering(client):
    res_all = client.get("/api/corpus")
    assert res_all.status_code == 200
    all_data = res_all.json()

    # Query with HSE role
    res_hse = client.get("/api/corpus?role=hse_specialist")
    assert res_hse.status_code == 200
    hse_data = res_hse.json()

    # HSE should not see 04_SAP or 05_Correspondence
    for src in hse_data.get("sources", []):
        path = src.get("relPath", "") or src.get("fullPath", "")
        assert "04_SAP_Mock_Exports" not in path
        assert "05_Correspondence" not in path

    # HSE count should be less than or equal to unrestricted count
    assert hse_data.get("count", 0) <= all_data.get("count", 0)


def test_api_search_with_role_refusal(client, monkeypatch):
    from backend.retrieval.grounded_retrieval import GroundedRetrievalResult
    from backend.retrieval.hybrid_search import RetrievedChunk

    # Mock retrieve_with_grounding_check to return a single SAP chunk
    def mock_retrieve(store, query, top_k=5):
        chunk = RetrievedChunk(
            text="SAP material 1002345 price 450.00",
            source_document="04_SAP_Mock_Exports/MM_Pricing.csv",
            page_number=1,
            score=0.92,
        )
        return GroundedRetrievalResult(found=True, chunks=[chunk])

    import backend.retrieval.grounded_retrieval as gr
    monkeypatch.setattr(gr, "retrieve_with_grounding_check", mock_retrieve)

    # Search as HSE (forbidden from SAP) -> refusal
    res_hse = client.post("/api/search", json={"query": "material pricing", "role": "hse_specialist"})
    assert res_hse.status_code == 200
    data_hse = res_hse.json()
    assert data_hse["found"] is False
    assert "Access restricted" in data_hse["reason"]
    assert len(data_hse["chunks"]) == 0

    # Search as Plant Engineer (permitted for SAP) -> found
    res_eng = client.post("/api/search", json={"query": "material pricing", "role": "plant_engineer"})
    assert res_eng.status_code == 200
    data_eng = res_eng.json()
    assert data_eng["found"] is True
    assert len(data_eng["chunks"]) == 1
