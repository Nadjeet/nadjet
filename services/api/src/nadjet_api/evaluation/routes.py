"""``GET /evaluation/latest``: the latest evaluation results (supervisor, admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from nadjet_api.auth.deps import require_roles
from nadjet_api.auth.models import User
from nadjet_api.auth.roles import Role
from nadjet_api.config import Settings
from nadjet_api.evaluation.store import latest_results
from nadjet_shared.evaluation import EvaluationResults

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

SupervisorUser = Annotated[User, Depends(require_roles(Role.SUPERVISOR, Role.ADMIN))]


@router.get(
    "/latest",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Role"},
        404: {"description": "No evaluation has been run"},
    },
)
async def latest_evaluation(request: Request, _user: SupervisorUser) -> EvaluationResults:
    """Precision, recall, F1, delay, false alarms per camera-hour and the ablation table of the
    newest run on the evaluation clips, with what was not run and the limitations."""
    settings: Settings = request.app.state.settings
    results = latest_results(settings.evaluation_dir)
    if results is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation results yet")
    return results
