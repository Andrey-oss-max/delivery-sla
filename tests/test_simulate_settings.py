from sla.rules import validate_row
from sla.settings import Settings
from sla.simulate import generate
from helpers import CAL, NOW, ZONES


def test_same_seed_same_data():
    assert generate(ZONES, 50, NOW, seed=5, calendar=CAL) == generate(ZONES, 50, NOW, seed=5, calendar=CAL)
    assert generate(ZONES, 50, NOW, seed=5, calendar=CAL) != generate(ZONES, 50, NOW, seed=6, calendar=CAL)


def test_generator_injects_faults_that_rules_catch():
    rows = generate(ZONES, 300, NOW, seed=1, calendar=CAL)
    bad = [r for _, r in rows if validate_row(r, ZONES, NOW)[1]]
    assert 0 < len(bad) < len(rows) * 0.2


def test_without_faults_all_rows_are_valid():
    rows = generate(ZONES, 200, NOW, seed=3, fault_rate=0, calendar=CAL)
    assert all(not validate_row(r, ZONES, NOW)[1] for _, r in rows)


def test_settings_from_env_dict():
    s = Settings.from_env({"DB_HOST": "db", "DB_PORT": "3307", "SLA_TARGET": "90", "REPORT_NOW": "2026-11-06T18:00"})
    assert (s.db_host, s.db_port, s.sla_target) == ("db", 3307, 90.0)
    assert s.now() == NOW
