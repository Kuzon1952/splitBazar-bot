from datetime import datetime, timezone, timedelta

# Moscow time = UTC+3
MOSCOW_TZ = timezone(timedelta(hours=3))


def now_moscow() -> datetime:
    """Return current datetime in Moscow time (UTC+3)."""
    return datetime.now(tz=MOSCOW_TZ).replace(tzinfo=None)


def today_moscow():
    """Return today's date in Moscow time."""
    return now_moscow().date()
