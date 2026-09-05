"""
FastAPI Application Entrypoint:
Quản lý vòng đời ứng dụng, phục vụ API endpoints và Static Frontend.
Chạy trực tiếp:
    uvicorn src.api.main:app --reload
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.scheduler.reminder_scheduler import start_scheduler, shutdown_scheduler
from src.api.routes import router
from src.api.evaluation_router import eval_router
from fastapi.responses import RedirectResponse

# Cấu hình logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("FastAPIServer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý khởi động và dọn dẹp tài nguyên."""
    logger.info("=== KHOI DONG HE THONG AI ACADEMIC ADVISOR ===")
    settings.ensure_directories()
    start_scheduler()
    yield
    logger.info("=== DANG TAT HE THONG ===")
    shutdown_scheduler()


app = FastAPI(
    title="AI Academic Advisor - Khoa CNTT Dai Nam",
    description="Agentic RAG Assistant ho tro co van hoc tap",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau.",
            }
        },
    )


# Đăng ký routes
app.include_router(router)
app.include_router(eval_router)


@app.get("/evaluation", include_in_schema=False)
async def redirect_evaluation():
    return RedirectResponse(url="/evaluation/")

# Phục vụ Frontend Static Files
_frontend_dir = settings.BASE_DIR / "frontend"
_frontend_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
