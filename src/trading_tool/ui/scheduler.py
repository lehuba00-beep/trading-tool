"""Zeitgesteuerte Laeufe - dreimal taeglich, an den Handelszeiten ausgerichtet.

09:30  kurz nach Xetra-Eroeffnung; die US-Tagesbalken des Vortags sind final.
14:00  vor US-Handelsbeginn; Zwischenstand des europaeischen Tages.
22:30  nach US-Schluss; erst hier sind alle Tagesbalken endgueltig.

Die Zwischenstaende beruhen auf noch nicht abgeschlossenen Tagesbalken. Die
daraus entstehenden Signale werden in der Oberflaeche als vorlaeufig markiert.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Settings

log = logging.getLogger(__name__)


class ScreeningScheduler:
    def __init__(self, settings: Settings, trigger_all: Callable[[str], None]) -> None:
        self.settings = settings
        self.trigger_all = trigger_all
        self.scheduler: BackgroundScheduler | None = None

    def start(self) -> None:
        if not self.settings.schedule.enabled:
            log.info("Zeitsteuerung deaktiviert")
            return
        try:
            self.scheduler = BackgroundScheduler(timezone=self.settings.schedule.timezone)
        except Exception as exc:
            log.warning("Zeitzone %s unbrauchbar (%s) - Zeitsteuerung aus",
                        self.settings.schedule.timezone, exc)
            return

        for hour, minute in self.settings.schedule.as_hour_minute():
            self.scheduler.add_job(
                self._run,
                CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute),
                args=[f"{hour:02d}:{minute:02d}"],
                id=f"screening_{hour:02d}{minute:02d}",
                # Nach einem Standby des Rechners duerfen verpasste Laeufe nicht
                # gesammelt nachfeuern.
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
        self.scheduler.start()
        log.info("Zeitsteuerung aktiv: %s (%s)",
                 ", ".join(self.settings.schedule.times), self.settings.schedule.timezone)

    def shutdown(self) -> None:
        if self.scheduler:
            self.scheduler.shutdown(wait=False)

    def _run(self, label: str) -> None:
        log.info("Geplanter Lauf %s", label)
        self.trigger_all(label)

    def next_runs(self) -> list[str]:
        if not self.scheduler:
            return []
        return [
            job.next_run_time.strftime("%d.%m.%Y %H:%M")
            for job in self.scheduler.get_jobs()
            if job.next_run_time
        ]
