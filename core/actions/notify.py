"""Owner alert + work-order stub for the appliance path (Day 7).

A stub, not a real SMS provider: it builds the alert and work order the
dashboard shows, with stable IDs the demo can reference. Pure function, no
credentials and no network.
"""

from __future__ import annotations

from uuid import uuid4

from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import ApplianceAlert, Runbook


def send_alert(
    diagnosis: Diagnosis,
    runbook: Runbook,
    attempts: int = 1,
    model_used: str = "",
) -> ApplianceAlert:
    """Build the owner SMS text and technician work order for a validated runbook."""
    alert_id = f"alert-{uuid4().hex[:8]}"
    work_order_id = f"wo-{uuid4().hex[:8]}"
    steps = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(runbook.steps))
    message = (
        f"TelemetryAgent: abnormal behavior detected ({diagnosis.summary}). "
        f"Likely cause: {diagnosis.likely_cause}. "
        f"Safety-checked runbook {work_order_id} is ready; "
        f"hold at {runbook.target_temperature_c}°C."
    )
    work_order = (
        f"Work order {work_order_id} (diagnosed in {attempts} attempt(s)"
        + (f" via {model_used}" if model_used else "")
        + f"):\n{steps}\n"
        f"Hold at {runbook.target_temperature_c}°C; "
        f"restart delay {runbook.restart_delay_s}s; "
        f"max power-off {runbook.power_off_minutes} min."
    )
    return ApplianceAlert(
        alert_id=alert_id,
        channel="sms-stub",
        message=message,
        work_order_id=work_order_id,
        work_order=work_order,
    )
