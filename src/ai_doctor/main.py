from __future__ import annotations

import uvicorn

from ai_doctor.api import create_app

app = create_app()


def run() -> None:
    uvicorn.run("ai_doctor.main:app", host="127.0.0.1", port=8080, reload=False)


if __name__ == "__main__":
    run()
