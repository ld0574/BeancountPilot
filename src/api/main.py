"""
FastAPI main application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import upload, classify, feedback, generate

# Create FastAPI application
app = FastAPI(
    title="BeancountPilot API",
    description="AI-powered intelligent transaction classification and workflow enhancement tool",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(classify.router, prefix="/api", tags=["classify"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(generate.router, prefix="/api", tags=["generate"])


@app.get("/")
async def root():
    """Root path"""
    return {
        "message": "BeancountPilot API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy"}


# Startup event
@app.on_event("startup")
async def startup_event():
    """Execute on application startup"""
    from src.db.session import init_db

    init_db()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
