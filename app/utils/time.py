from datetime import datetime, timedelta


def is_expired(updated_at: datetime, ttl_hours: int) -> bool:
    return datetime.utcnow() - updated_at > timedelta(hours=ttl_hours)
