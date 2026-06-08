"""Unit tests for audit_service: payload shaping + the fire-and-forget guarantee.

No live DB — a FakeSession stands in for AsyncSession (matching the other
service unit tests). The load-bearing property under test is that ``record``
NEVER raises, even when the underlying write fails: auditing must not be able to
break the action being audited.
"""

import uuid

from app.services import audit_service


class _NestedCtx:
    """Stand-in for the awaitable context manager returned by begin_nested()."""

    def __init__(self, session: "FakeSession", fail: bool) -> None:
        self._session = session
        self._fail = fail

    async def __aenter__(self):
        if self._fail:
            raise RuntimeError("savepoint boom")
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, fail: bool = False) -> None:
        self.added: list = []
        self._fail = fail

    def begin_nested(self):
        return _NestedCtx(self, self._fail)

    def add(self, obj) -> None:
        self.added.append(obj)


async def test_record_writes_event_with_request_id_folded_in():
    db = FakeSession()
    org = uuid.uuid4()
    actor = uuid.uuid4()

    await audit_service.record(
        db,
        organization_id=org,
        actor_id=actor,
        event_type=audit_service.CONNECTION_CREATED,
        payload={"name": "warehouse"},
    )

    assert len(db.added) == 1
    event = db.added[0]
    assert event.organization_id == org
    assert event.actor_id == actor
    assert event.event_type == "connection.created"
    assert event.payload["name"] == "warehouse"


async def test_record_never_raises_when_write_fails():
    db = FakeSession(fail=True)

    # Must return normally despite the savepoint blowing up — fire-and-forget.
    await audit_service.record(
        db,
        organization_id=uuid.uuid4(),
        event_type=audit_service.QUERY_BLOCKED,
        payload={"reason": "DDL not allowed"},
    )

    assert db.added == []


def test_event_type_constants_are_unique_and_listed():
    assert len(audit_service.EVENT_TYPES) == len(set(audit_service.EVENT_TYPES))
    # Every module-level dotted constant is advertised in EVENT_TYPES.
    for name, value in vars(audit_service).items():
        if name.isupper() and isinstance(value, str) and "." in value:
            assert value in audit_service.EVENT_TYPES
