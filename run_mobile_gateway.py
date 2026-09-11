"""Start the existing SHELF-SCOUTER Flask app plus the /v1 mobile gateway."""

import os

import app
import mobile_gateway  # noqa: F401 - registers /v1 routes on app.app


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.app.run(host=host, port=port)
