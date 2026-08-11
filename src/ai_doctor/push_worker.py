from __future__ import annotations

import json
import time
from typing import Any, Dict

from pywebpush import WebPushException, webpush

from ai_doctor.relay import GENERIC_PUSH_MESSAGE, OpaqueRelayRepository
from ai_doctor.settings import Settings


class GenericPushWorker:
    """Deliver generic wake-up notifications only.

    Provider acceptance is recorded separately from display and acknowledgement.
    This worker has no clinical facts, severity, instruction, or contact data.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = OpaqueRelayRepository(settings.database_path)

    def run_once(self) -> int:
        attempted = 0
        for schedule in self.repository.claim_due_schedules():
            accepted = self._send(schedule)
            self.repository.finish_push_attempt(
                schedule["opaque_schedule_id"], accepted=accepted
            )
            attempted += 1
        return attempted

    def _send(self, schedule: Dict[str, Any]) -> bool:
        if not (
            self.settings.push_enabled
            and self.settings.push_vapid_private_key
            and self.settings.push_vapid_subject
        ):
            return False
        subscription = {
            "endpoint": schedule["endpoint"],
            "keys": {"p256dh": schedule["p256dh"], "auth": schedule["auth"]},
        }
        try:
            webpush(
                subscription_info=subscription,
                data=json.dumps({"message": GENERIC_PUSH_MESSAGE}),
                vapid_private_key=self.settings.push_vapid_private_key,
                vapid_claims={"sub": self.settings.push_vapid_subject},
                timeout=10,
            )
            return True
        except WebPushException:
            return False


def run() -> None:
    settings = Settings.from_env()
    worker = GenericPushWorker(settings)
    while True:
        worker.run_once()
        time.sleep(30)


if __name__ == "__main__":
    run()
