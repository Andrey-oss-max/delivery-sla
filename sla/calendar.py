"""Рабочий календарь службы доставки: выходные, праздники, время отсечки приёма заказов."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class WorkCalendar:
    holidays: frozenset = field(default_factory=frozenset)
    cutoff: time = time(14, 0)    # заказ после отсечки начинают собирать на следующий рабочий день
    day_end: time = time(21, 0)   # до этого времени курьеры доставляют в рабочий день

    def is_working(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def next_working(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.is_working(d):
            d += timedelta(days=1)
        return d

    def start_day(self, created: datetime) -> date:
        """День, когда заказ принят в работу."""
        d = created.date()
        if self.is_working(d) and created.time() < self.cutoff:
            return d
        return self.next_working(d)

    def standard_deadline(self, created: datetime, days: int) -> datetime:
        """Конец days-го рабочего дня после дня приёма в работу."""
        d = self.start_day(created)
        for _ in range(days):
            d = self.next_working(d)
        return datetime.combine(d, self.day_end)

    @staticmethod
    def express_deadline(created: datetime, hours: int) -> datetime:
        return created + timedelta(hours=hours)
