from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import Field

from ai_doctor.auth import Principal, TokenAuthenticator, require_roles
from ai_doctor.capabilities.prescribing import (
    Ed25519ProtocolVerifier,
    ProtocolRepository,
)
from ai_doctor.domain.models import (
    CaseCreate,
    CaseCreated,
    ClinicalDecision,
    PatientAdvice,
    PatientSnapshot,
    ReviewRequest,
    StrictModel,
    UserRole,
)
from ai_doctor.models.gateway import (
    DiagnosisModelGateway,
    OpenAICompatibleTransport,
)
from ai_doctor.observability import install_observability
from ai_doctor.orchestrator import ClinicalOrchestrator, ClinicalWorkflowError
from ai_doctor.relay import mount_longitudinal_routes
from ai_doctor.settings import Settings
from ai_doctor.storage.sqlite import (
    CaseNotFoundError,
    ConcurrentModificationError,
    SqliteRepository,
)


class CaseView(StrictModel):
    case_id: UUID
    snapshot: PatientSnapshot
    decision: ClinicalDecision


class PrescriptionDraftCreate(StrictModel):
    protocol_id: str = Field(min_length=1, max_length=200)


class AccessGrant(StrictModel):
    principal_id: str = Field(min_length=1, max_length=200)
    access_level: str = Field(pattern="^(read|read_write)$")


class CapabilityView(StrictModel):
    registry_version: str
    releases: Dict[str, str]
    provenance: Dict[str, Dict[str, str]]
    preclinical: bool = True


def create_app(
    settings: Optional[Settings] = None,
    protocol_repository: Optional[ProtocolRepository] = None,
    diagnosis_model_gateway: Optional[DiagnosisModelGateway] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    repository = SqliteRepository(settings.database_path)
    authenticator = TokenAuthenticator(settings.tokens)
    if protocol_repository is None and settings.protocol_path is not None:
        verifier = (
            Ed25519ProtocolVerifier(settings.protocol_public_keys)
            if settings.protocol_public_keys
            else None
        )
        protocol_repository = ProtocolRepository.from_file(
            settings.protocol_path,
            signature_verifier=verifier,
            allow_test_fixtures=settings.allow_test_protocols,
        )
    if diagnosis_model_gateway is None and settings.model_gateway_enabled:
        # Settings validates endpoint and model whenever this opt-in is enabled.
        diagnosis_model_gateway = DiagnosisModelGateway(
            transport=OpenAICompatibleTransport(
                endpoint=settings.model_gateway_endpoint or "",
                model=settings.model_gateway_model or "",
                api_key=settings.model_gateway_api_key,
                timeout_seconds=settings.model_gateway_timeout_seconds,
            ),
            model_release=settings.model_gateway_release,
        )
    orchestrator = ClinicalOrchestrator(
        repository=repository,
        protocol_repository=protocol_repository,
        diagnosis_model_gateway=diagnosis_model_gateway,
        emergency_service_label=settings.emergency_service_label,
    )
    authenticate = authenticator.dependency()

    app = FastAPI(
        title="AI Doctor Preclinical Clinical Decision Platform",
        version="0.1.0",
        description=(
            "Preclinical clinician-supervised implementation. It is not a licensed "
            "medical service and cannot execute prescriptions or replace emergency care."
        ),
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.orchestrator = orchestrator

    @app.middleware("http")
    async def clinical_response_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-AI-Doctor-Environment"] = settings.environment
        response.headers["X-Clinical-Authority"] = "preclinical-clinician-supervised"
        return response

    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_handler(request: Request, error: CaseNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Case not found"})

    @app.exception_handler(ClinicalWorkflowError)
    async def workflow_handler(request: Request, error: ClinicalWorkflowError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ConcurrentModificationError)
    async def concurrent_modification_handler(
        request: Request, error: ConcurrentModificationError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(PermissionError)
    async def permission_handler(request: Request, error: PermissionError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    def require_case_access(case_id: UUID, principal: Principal, *, write: bool = False) -> None:
        if not repository.has_access(
            case_id,
            principal.user_id,
            principal.role.value,
            write=write,
        ):
            # Do not reveal whether a case exists to an unauthorized principal.
            raise HTTPException(status_code=404, detail="Case not found")

    @app.get("/")
    def root() -> Dict[str, Any]:
        return {
            "service": "AI Doctor Preclinical Clinical Decision Platform",
            "status": "preclinical",
            "clinical_authority": "none",
            "prescription_execution": False,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "environment": settings.environment,
            "preclinical": True,
        }

    @app.get("/v1/capabilities", response_model=CapabilityView)
    def capabilities(
        principal: Principal = Depends(authenticate),
    ) -> CapabilityView:
        registry = orchestrator.safety_gate.registry
        from ai_doctor.domain.models import CapabilityName

        return CapabilityView(
            registry_version=registry.registry_version,
            releases=registry.release_versions(list(CapabilityName)),
            provenance=registry.provenance_for(list(CapabilityName)),
        )

    @app.post(
        "/v1/cases",
        response_model=CaseCreated,
        status_code=status.HTTP_201_CREATED,
    )
    def create_case_endpoint(
        request: CaseCreate,
        principal: Principal = Depends(authenticate),
    ) -> CaseCreated:
        require_roles(
            principal,
            {
                UserRole.PATIENT,
                UserRole.PHYSICIAN,
                UserRole.PHARMACIST,
                UserRole.NURSE,
            },
        )
        return orchestrator.create_case(request, principal)

    @app.get("/v1/cases/{case_id}", response_model=CaseView)
    def get_case_endpoint(
        case_id: UUID,
        principal: Principal = Depends(authenticate),
    ) -> CaseView:
        require_case_access(case_id, principal)
        snapshot, decision = orchestrator.get_case(case_id)
        return CaseView(case_id=case_id, snapshot=snapshot, decision=decision)

    @app.get("/v1/cases/{case_id}/versions")
    def case_versions_endpoint(
        case_id: UUID,
        principal: Principal = Depends(authenticate),
    ) -> List[Dict[str, Any]]:
        require_case_access(case_id, principal)
        return repository.list_case_versions(case_id)

    @app.post("/v1/cases/{case_id}/prescription-drafts", response_model=ClinicalDecision)
    def prescription_draft_endpoint(
        case_id: UUID,
        request: PrescriptionDraftCreate,
        principal: Principal = Depends(authenticate),
    ) -> ClinicalDecision:
        require_case_access(case_id, principal, write=True)
        return orchestrator.add_prescription_draft(case_id, request.protocol_id, principal)

    @app.post("/v1/cases/{case_id}/review", response_model=ClinicalDecision)
    def review_case_endpoint(
        case_id: UUID,
        review: ReviewRequest,
        principal: Principal = Depends(authenticate),
    ) -> ClinicalDecision:
        require_case_access(case_id, principal, write=True)
        return orchestrator.review_case(case_id, review, principal)

    @app.get("/v1/cases/{case_id}/advice", response_model=PatientAdvice)
    def patient_advice_endpoint(
        case_id: UUID,
        principal: Principal = Depends(authenticate),
    ) -> PatientAdvice:
        require_case_access(case_id, principal)
        return orchestrator.get_patient_advice(case_id, principal)

    @app.get("/v1/cases/{case_id}/audit")
    def case_audit_endpoint(
        case_id: UUID,
        principal: Principal = Depends(authenticate),
    ) -> List[Dict[str, Any]]:
        require_case_access(case_id, principal)
        return repository.list_events(case_id)

    @app.get("/v1/cases/{case_id}/audit/verify")
    def verify_case_audit_endpoint(
        case_id: UUID,
        principal: Principal = Depends(authenticate),
    ) -> Dict[str, Any]:
        require_case_access(case_id, principal)
        return repository.verify_event_chain(case_id)

    @app.post("/v1/cases/{case_id}/access", status_code=status.HTTP_204_NO_CONTENT)
    def grant_case_access_endpoint(
        case_id: UUID,
        grant: AccessGrant,
        principal: Principal = Depends(authenticate),
    ) -> Response:
        require_roles(
            principal,
            {UserRole.PHYSICIAN, UserRole.CLINICAL_SAFETY_OFFICER},
        )
        require_case_access(case_id, principal, write=True)
        repository.grant_access(
            case_id=case_id,
            principal_id=grant.principal_id,
            access_level=grant.access_level,
            granted_by=principal.user_id,
            granted_by_role=principal.role.value,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    mount_longitudinal_routes(
        app,
        authenticate=authenticate,
        settings=settings,
        release_manifest_path=(
            settings.release_manifest_path
            or Path(__file__).resolve().parent / "config" / "release_manifest_v3.json"
        ),
    )

    install_observability(app, settings)
    return app
