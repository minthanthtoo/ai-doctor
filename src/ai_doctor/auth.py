from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Dict, Iterable

from fastapi import Header, HTTPException, status

from ai_doctor.domain.models import UserRole


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: UserRole


class TokenAuthenticator:
    """Small preclinical bearer-token authenticator.

    Production deployments must replace this boundary with organization-managed
    OIDC/SMART authentication and authorization. The application refuses to use
    demonstration credentials when configured for production.
    """

    def __init__(self, token_records: Dict[str, Dict[str, str]]) -> None:
        self._records = dict(token_records)

    def authenticate_header(self, authorization: str) -> Principal:
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not credential:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A Bearer token is required",
            )

        matched = None
        for token, record in self._records.items():
            if secrets.compare_digest(token, credential):
                matched = record
                break
        if matched is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            )
        try:
            return Principal(
                user_id=matched["user_id"],
                role=UserRole(matched["role"]),
            )
        except (KeyError, ValueError) as error:
            raise RuntimeError("Invalid configured token record") from error

    def dependency(self):
        def authenticate(authorization: str = Header(default="")) -> Principal:
            return self.authenticate_header(authorization)

        return authenticate


def require_roles(principal: Principal, allowed: Iterable[UserRole]) -> None:
    allowed_set = set(allowed)
    if principal.role not in allowed_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {principal.role.value} is not permitted for this operation",
        )
