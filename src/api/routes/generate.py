"""
Generation routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.deg_integration import DoubleEntryGenerator
from src.api.schemas.transaction import GenerateRequest, GenerateResponse
from src.utils.config import get_config, expand_path

router = APIRouter()


def _create_deg() -> DoubleEntryGenerator:
    """Create DEG integration instance from app config."""
    executable = get_config("application.deg.executable", "double-entry-generator")
    config_dir_raw = get_config("application.deg.config_dir")
    config_dir = expand_path(config_dir_raw) if config_dir_raw else None
    return DoubleEntryGenerator(config_dir=config_dir, executable=executable)


@router.post("/generate", response_model=GenerateResponse)
async def generate_beancount(
    request: GenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Generate Beancount file

    Args:
        request: Generation request
        db: Database session

    Returns:
        Generation result
    """
    try:
        # Create DEG integrator
        deg = _create_deg()

        # Generate Beancount file
        result = deg.generate_beancount_from_transactions(
            transactions=request.transactions,
            provider=request.provider,
        )

        return GenerateResponse(
            success=result["success"],
            beancount_file=result.get("beancount_file", ""),
            message=result.get("message", ""),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/generate/check")
async def check_deg_installed():
    """
    Check if double-entry-generator is installed

    Returns:
        Check result
    """
    deg = _create_deg()
    status = deg.get_deg_status()
    installed = status["installed"]
    version = status.get("version", "")
    download_url = "https://github.com/deb-sig/double-entry-generator/releases"

    return {
        "installed": installed,
        "message": "double-entry-generator is installed" if installed else "double-entry-generator is not installed",
        "version": version,
        "download_url": download_url,
        "install_command": "double-entry-generator version",
    }
