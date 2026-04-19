"""SageMaker Model Monitor configuration stub (baseline + schedule placeholders)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MonitorSchedule:
    name: str
    cron_expression: str
    endpoint_name: str


def default_schedule(endpoint_name: str) -> MonitorSchedule:
    return MonitorSchedule(
        name="automotive-vlm-drift",
        cron_expression="cron(0 6 * * ? *)",
        endpoint_name=endpoint_name,
    )
