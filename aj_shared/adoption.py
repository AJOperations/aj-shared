"""Installed-package compatibility probe using package-owned synthetic data."""

import json
from importlib import resources
from .suite import validate_attention, ContractError


def check_compatibility(expected_major=1):
    with (
        resources.files("aj_shared")
        .joinpath("fixtures/attention-v1.json")
        .open() as source
    ):
        fixture = json.load(source)
    if fixture["schema_version"] != expected_major:
        raise ContractError("Incompatible expected attention contract")
    validate_attention(fixture, allowed_origin="https://synthetic.example")
    return {
        "attention_schema": fixture["schema_version"],
        "synthetic_items": len(fixture["items"]),
    }


if __name__ == "__main__":
    print(json.dumps(check_compatibility()))
