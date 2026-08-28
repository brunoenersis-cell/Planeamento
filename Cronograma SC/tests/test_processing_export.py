from data_processor import normalize_occurrences
from export_service import create_csv, create_excel
from schedule_service import sync_safetyculture_schedules


def test_normalizes_only_known_values():
    frame = normalize_occurrences([{ "schedule_id": "s1", "occurrence_id": "o1", "due_time": "2026-09-01T09:00:00Z", "occurrence_status": "TODO", "user_id": "u1" }])
    assert frame.loc[0, "Schedule ID"] == "s1"
    assert frame.loc[0, "Estado"] == "TODO"
    assert frame.loc[0, "Central"] is None
    assert frame.loc[0, "Data"] == "09/2026"
    assert frame.loc[0, "Data/hora limite"] == "2026-09-01T09:00:00Z"


def test_assigns_customer_from_local():
    frame = normalize_occurrences([{ "schedule_site_names": ["Reflexos"], "due_time": "2026-09-01T09:00:00Z" }])
    assert frame.loc[0, "Cliente"] == "REDEN"


def test_exports_are_created():
    frame = normalize_occurrences([{ "id": "x", "due_time": "2026-09-01T09:00:00Z" }])
    assert create_csv(frame).decode("utf-8-sig").startswith("Data")
    assert create_excel(frame).startswith(b"PK")


def test_sync_removes_duplicates():
    class Client:
        def fetch_all_pages(self, *_args): return [{"id": "one"}, {"id": "one"}, {"id": "two"}]
        def fetch_all_schedules(self, *_args): return []
        def fetch_all_sites(self): return []
    assert len(sync_safetyculture_schedules(Client(), "a", "b")) == 2


def test_sync_consolidates_assignees_for_one_occurrence():
    class Client:
        def fetch_all_pages(self, *_args):
            return [
                {"id": "one", "schedule_id": "schedule_1", "occurrence_id": "occurrence_1", "assignee_id": "user_1"},
                {"id": "two", "schedule_id": "schedule_1", "occurrence_id": "occurrence_1", "assignee_id": "user_2"},
            ]
        def fetch_all_schedules(self, *_args): return []
        def fetch_all_sites(self): return []
    rows = sync_safetyculture_schedules(Client(), "a", "b")
    assert len(rows) == 1
    assert rows[0]["assignee_ids"] == ["user_1", "user_2"]


def test_sync_adds_schedule_title():
    class Client:
        def fetch_all_pages(self, *_args): return [{"id": "one", "schedule_id": "schedule_1"}]
        def fetch_all_schedules(self, *_args): return [{"id": "scheduleitem_1", "title": "Reflexos - Inspeção aos Inversores", "site_ids": ["site_1"]}]
        def fetch_all_sites(self): return [{"id": "site_1", "name": "Reflexos"}]
    records = sync_safetyculture_schedules(Client(), "a", "b")
    assert records[0]["schedule_name"] == "Reflexos - Inspeção aos Inversores"
    assert records[0]["schedule_site_names"] == ["Reflexos"]


def test_sync_forecasts_future_schedule_not_yet_in_api():
    class Client:
        def fetch_all_pages(self, *_args): return []
        def fetch_all_schedules(self, *_args):
            return [{"id": "scheduleitem_1", "title": "Anual", "status": "ACTIVE", "recurrence": "DTSTART:20261201T090000\nRRULE:FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=1", "site_ids": []}]
        def fetch_all_sites(self): return []
    records = sync_safetyculture_schedules(Client(), "2026-12-01T00:00:00Z", "2026-12-31T23:59:59Z")
    assert len(records) == 1
    assert records[0]["occurrence_status"] == "PLANEADA"


def test_marks_forecast_origin():
    frame = normalize_occurrences([{ "planned_from_schedule": True, "due_time": "2026-12-01T09:00:00Z" }])
    assert frame.loc[0, "Origem"] == "Recorrência prevista"
