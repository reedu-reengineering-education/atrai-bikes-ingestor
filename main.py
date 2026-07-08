import uvicorn
from src.api import app


def main():
    """Run the FastAPI analytics server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()
