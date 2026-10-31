import logging

from fastapi import FastAPI

from app.api.v1.router import router
from app.core.errors import install_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = FastAPI(
    title="Hotel Booking API",
    version="1.0.0",
    description="Independent QA practice SUT. All payments are simulated. Dates and deadlines use UTC. "
    "Login with JSON at /api/v1/auth/login, then paste access_token into Authorize.",
    swagger_ui_parameters={"persistAuthorization": False},
)
install_handlers(app)
app.include_router(router)
