"""
Generation routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.deg_integration import DoubleEntryGenerator
from src.api.schemas.transaction import GenerateRequest, GenerateResponse

router = APIRouter()


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
        deg = DoubleEntryGenerator()

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
    deg = DoubleEntryGenerator()
    installed = deg.check_deg_installed()

    return {
        "installed": installed,
        "message": "double-entry-generator is installed" if installed else "double-entry-generator is not installed",
    }
