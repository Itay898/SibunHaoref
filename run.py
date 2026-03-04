"""Production entry point for Shower Radar."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,       # Single worker — we use in-memory state
        log_level="info",
        access_log=True,
    )
