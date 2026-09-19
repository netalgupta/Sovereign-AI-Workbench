"""Role-Based Access Control (RBAC) for Knowledge Base and Search.

FRONTEND.md §3.11, SYSTEM.md line 126, REQUIREMENTS.md line 53, TOOLS.md row 46.

Enforces role-tiered visibility across the MRPL sovereign corpus:
- 4 Role Tiers:
  * Plant Engineer (Operations Tier): SOPs, Inspection, Quality, SAP Mock, Diagrams. (No Depot Correspondence).
  * HSE Specialist (Safety Compliance Tier): SOPs, Inspection, Quality, Diagrams. (No SAP Mock, No Correspondence).
  * Superintendent / Approver (Executive Tier): Full visibility across all 6 categories.
  * System Administrator (Infrastructure Tier): Full visibility across all 6 categories.

- 6 Corpus Categories mapped to MRPL_RAG_Test_Corpus subdirectories:
  * sops -> 01_SOPs_and_Procedures
  * inspection -> 02_Inspection_and_Maintenance
  * quality -> 03_Quality_and_Process_Data
  * sap_mock -> 04_SAP_Mock_Exports
  * correspondence -> 05_Correspondence
  * diagrams -> 06_Diagrams_and_Scans
  * user_uploads -> 07_User_Uploads (open to all authorized roles)
"""

from typing import Any


RBAC_CATEGORIES = [
    {
        "id": "sops",
        "label": "01_SOPs & Safety (HCU-2 & Aromatics)",
        "folder": "01_SOPs_and_Procedures",
        "folder_prefix": "01_SOPs",
    },
    {
        "id": "inspection",
        "label": "02_Inspection & Maintenance (CCR-1 & Hassan)",
        "folder": "02_Inspection_and_Maintenance",
        "folder_prefix": "02_Inspection",
    },
    {
        "id": "quality",
        "label": "03_Quality & Process Data (Novolen QA & Merox)",
        "folder": "03_Quality_and_Process_Data",
        "folder_prefix": "03_Quality",
    },
    {
        "id": "sap_mock",
        "label": "04_SAP ERP Mock Records (Materials Master)",
        "folder": "04_SAP_Mock_Exports",
        "folder_prefix": "04_SAP",
    },
    {
        "id": "correspondence",
        "label": "05_Depot Correspondence (Kasargod)",
        "folder": "05_Correspondence",
        "folder_prefix": "05_Correspondence",
    },
    {
        "id": "diagrams",
        "label": "06_Diagrams & Scans (P&ID & OCR Checklist)",
        "folder": "06_Diagrams_and_Scans",
        "folder_prefix": "06_Diagrams",
    },
]

# Map directory folder name prefixes to category id
FOLDER_TO_CATEGORY: dict[str, str] = {
    "01_sops_and_procedures": "sops",
    "01_sops": "sops",
    "02_inspection_and_maintenance": "inspection",
    "02_inspection": "inspection",
    "03_quality_and_process_data": "quality",
    "03_quality": "quality",
    "04_sap_mock_exports": "sap_mock",
    "04_sap": "sap_mock",
    "05_correspondence": "correspondence",
    "06_diagrams_and_scans": "diagrams",
    "06_diagrams": "diagrams",
}

RBAC_TIERS = [
    {
        "role_id": "plant_engineer",
        "role": "Plant Engineer",
        "badge": "Operations Tier",
        "description": "Operational troubleshooting, sensor telemetry, and standard operating procedure lookup.",
        "permissions": {
            "sops": True,
            "inspection": True,
            "quality": True,
            "sap_mock": True,
            "correspondence": False,
            "diagrams": True,
        },
    },
    {
        "role_id": "hse_specialist",
        "role": "HSE Specialist",
        "badge": "Safety Compliance Tier",
        "description": "Health, Safety & Environment compliance, runaway prevention guidelines, and safety interlock review.",
        "permissions": {
            "sops": True,
            "inspection": True,
            "quality": True,
            "sap_mock": False,
            "correspondence": False,
            "diagrams": True,
        },
    },
    {
        "role_id": "superintendent",
        "role": "Superintendent / Approver",
        "badge": "Executive Authorization Tier",
        "description": "Management of Change (MOC) sign-off, critical parameter overrides, and cross-unit economic optimization.",
        "permissions": {
            "sops": True,
            "inspection": True,
            "quality": True,
            "sap_mock": True,
            "correspondence": True,
            "diagrams": True,
        },
    },
    {
        "role_id": "system_admin",
        "role": "System Administrator",
        "badge": "Infrastructure Tier",
        "description": "Air-gapped model registry orchestration, hardware encryption keys, and network interface security.",
        "permissions": {
            "sops": True,
            "inspection": True,
            "quality": True,
            "sap_mock": True,
            "correspondence": True,
            "diagrams": True,
        },
    },
]

# Role alias map for flexible matching
ROLE_ALIASES: dict[str, str] = {
    "plant_engineer": "plant_engineer",
    "plant engineer": "plant_engineer",
    "engineer": "plant_engineer",
    "operations": "plant_engineer",
    "hse_specialist": "hse_specialist",
    "hse specialist": "hse_specialist",
    "hse": "hse_specialist",
    "safety": "hse_specialist",
    "superintendent": "superintendent",
    "approver": "superintendent",
    "superintendent / approver": "superintendent",
    "executive": "superintendent",
    "system_admin": "system_admin",
    "system administrator": "system_admin",
    "admin": "system_admin",
    "administrator": "system_admin",
}

TIERS_BY_ID: dict[str, dict] = {tier["role_id"]: tier for tier in RBAC_TIERS}


def normalize_role(role: str | None) -> str | None:
    """Normalize user-provided role string to standard role_id."""
    if not role:
        return None
    cleaned = role.strip().lower()
    return ROLE_ALIASES.get(cleaned, cleaned)


def get_category_for_path(path_or_doc: str) -> str | None:
    """Determine the RBAC category from a file name or relative/absolute path."""
    if not path_or_doc:
        return None
    normalized = path_or_doc.replace("\\", "/").lower()
    parts = [p.strip() for p in normalized.split("/") if p.strip()]

    # Check parts against known folder prefixes
    for part in parts:
        for prefix, cat_id in FOLDER_TO_CATEGORY.items():
            if part.startswith(prefix) or prefix in part:
                return cat_id

    # Also check if filename itself contains category prefix
    filename = parts[-1] if parts else normalized
    for prefix, cat_id in FOLDER_TO_CATEGORY.items():
        if filename.startswith(prefix):
            return cat_id

    return None


def is_category_allowed(role: str | None, category_id: str | None) -> bool:
    """Check if a role is permitted to access a given category.

    If role is None, access is permitted (default unauthenticated/open dev mode).
    If category_id is unknown or None (e.g. user upload or general note), access is permitted.
    """
    if not role:
        return True
    if not category_id:
        return True

    norm_role = normalize_role(role)
    tier = TIERS_BY_ID.get(norm_role)
    if not tier:
        # Unknown role defaults to restricted or False if unrecognized
        return False

    return tier["permissions"].get(category_id, False)


def is_path_allowed(role: str | None, path_or_doc: str) -> bool:
    """Check if a role is permitted to access a document path."""
    if not role:
        return True
    cat_id = get_category_for_path(path_or_doc)
    if cat_id is None:
        return True
    return is_category_allowed(role, cat_id)


def filter_chunks_by_role(role: str | None, chunks: list[Any]) -> list[Any]:
    """Filter retrieved chunks so only passages from permitted categories are returned."""
    if not role:
        return chunks

    allowed_chunks = []
    for chunk in chunks:
        # chunk can be a GroundedChunk object or a dict
        source_doc = getattr(chunk, "source_document", None)
        if source_doc is None and isinstance(chunk, dict):
            source_doc = chunk.get("source_document") or chunk.get("document") or ""

        if is_path_allowed(role, str(source_doc)):
            allowed_chunks.append(chunk)

    return allowed_chunks


def filter_corpus_tree(
    role: str | None,
    tree: list[dict],
    directories: list[dict],
    sources: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Filter corpus data (tree, directories, sources) according to role permissions."""
    if not role:
        return tree, directories, sources

    filtered_sources = [
        s for s in sources
        if is_path_allowed(role, s.get("relPath", "") or s.get("fullPath", "") or s.get("name", ""))
    ]

    def _filter_node(node: dict) -> dict | None:
        path = node.get("relPath", "") or node.get("fullPath", "") or node.get("name", "")
        # If directory, filter children
        if node.get("type") == "directory":
            cat = get_category_for_path(path)
            if cat and not is_category_allowed(role, cat):
                return None
            filtered_children = []
            for child in node.get("children", []):
                filtered_child = _filter_node(child)
                if filtered_child is not None:
                    filtered_children.append(filtered_child)
            new_node = dict(node)
            new_node["children"] = filtered_children
            new_node["fileCount"] = sum(
                1 if c.get("type") == "file" else c.get("fileCount", 0) for c in filtered_children
            )
            new_node["totalSizeBytes"] = sum(
                c.get("sizeBytes", 0) if c.get("type") == "file" else c.get("totalSizeBytes", 0)
                for c in filtered_children
            )
            return new_node
        else:
            # File
            if is_path_allowed(role, path):
                return node
            return None

    filtered_tree = []
    for root_node in tree:
        fn = _filter_node(root_node)
        if fn is not None:
            filtered_tree.append(fn)

    filtered_dirs = [
        d for d in directories
        if is_path_allowed(role, d.get("path", "") or d.get("name", ""))
    ]

    return filtered_tree, filtered_dirs, filtered_sources


def get_rbac_manifest() -> dict[str, Any]:
    """Authoritative RBAC manifest for UI and API consumption."""
    return {
        "tiers": RBAC_TIERS,
        "categories": RBAC_CATEGORIES,
        "role_aliases": ROLE_ALIASES,
    }
