"""Validate explicitly supplied build identity and expose a safe support subset.

No environment scanning, Git invocation or hosting observation is performed.
"""

import re
from .suite import fields, identifier, timestamp, ContractError

UNKNOWN = "Unknown"


def validate_runtime(value):
    result = fields(
        value,
        (
            "schema_version",
            "app_id",
            "environment",
            "source_revision",
            "artifact_digest",
            "build_time",
            "shared_version",
            "shared_checksum",
            "ui_version",
            "ui_checksum",
            "support_owner",
        ),
        ("release_version", "api_contracts", "schema_required"),
    )
    if type(result["schema_version"]) is not int or result["schema_version"] != 1:
        raise ContractError("Unsupported runtime schema")
    for key in ("app_id", "environment", "support_owner"):
        identifier(result[key])
    if result["source_revision"] != UNKNOWN and (
        type(result["source_revision"]) is not str
        or not re.fullmatch(r"[0-9a-f]{40}", result["source_revision"])
    ):
        raise ContractError("Invalid source revision")
    for key in ("artifact_digest", "shared_checksum", "ui_checksum"):
        if result[key] != UNKNOWN and (
            type(result[key]) is not str
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", result[key])
        ):
            raise ContractError("Invalid artifact checksum")
    for key in ("shared_version", "ui_version", "release_version"):
        if (
            key in result
            and result[key] != UNKNOWN
            and (
                type(result[key]) is not str
                or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", result[key])
            )
        ):
            raise ContractError("Invalid release version")
    if result["build_time"] != UNKNOWN:
        timestamp(result["build_time"])
    if "schema_required" in result and (
        type(result["schema_required"]) is not int or result["schema_required"] < 1
    ):
        raise ContractError("Invalid schema requirement")
    if "api_contracts" in result:
        if (
            type(result["api_contracts"]) is not list
            or len(result["api_contracts"]) > 20
        ):
            raise ContractError("Invalid API contracts")
        for contract in result["api_contracts"]:
            if type(contract) is not str or not re.fullmatch(
                r"[a-z0-9/-]{1,64}", contract
            ):
                raise ContractError("Invalid API contract")
    return result


def support_identity(value, *, privileged=False):
    result = validate_runtime(value)
    if privileged is True:
        return result
    return {key: result[key] for key in ("schema_version", "app_id", "support_owner")}
