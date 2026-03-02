from fastapi import HTTPException

from scheduler.api.admin import _validated_domain_name
from scheduler.utils.redis_acl import worker_acl_username


def test_validated_domain_name_accepts_strict_values():
    assert _validated_domain_name("prod") == "prod"
    assert _validated_domain_name("dev_01") == "dev_01"
    assert _validated_domain_name("qa-team") == "qa-team"


def test_validated_domain_name_rejects_invalid_values():
    invalid = ["", "Proud", "a", "team.", "-team", "team-", "team space", "x" * 64]
    for value in invalid:
        try:
            _validated_domain_name(value)
            assert False, f"expected HTTPException for value: {value}"
        except HTTPException as exc:
            assert exc.status_code == 400


def test_worker_acl_username_is_domain_name():
    assert worker_acl_username("prod") == "prod"
    assert worker_acl_username("dev_01") == "dev_01"
