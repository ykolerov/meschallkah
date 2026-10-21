import csv

import pytest

import sweep


def test_make_table_sweeps_up_and_down():
    values = sweep.make_values(200, 1500, 700, 0.25, 0.02, 0.08)
    peak = values.index(1500)
    assert values[0] == values[-1] == 200
    assert values[:peak + 1] == sorted(values[:peak + 1])
    assert values[peak:] == sorted(values[peak:], reverse=True)


def test_bad_schedule_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("rpm,wait_s,record_s\n100,-1,4\n")
    with pytest.raises(ValueError):
        sweep.read_table(path)


def test_fclk_calibration():
    k, clock, se, residuals = sweep.fit_clock([200, 800, 1600],
                                             [202, 808, 1616])
    assert k == pytest.approx(1.01)
    assert clock == pytest.approx(12.12e6)
    assert max(abs(x) for x in residuals) < 1e-6


def test_command_line_dry_run_full_cycle(tmp_path):
    steps = tmp_path / "steps.csv"
    logfile = tmp_path / "result.csv"
    assert sweep.main(["make-table", "--lo", "60", "--hi", "120", "--center",
                       "90", "--wait", "0", "--record", "0.1",
                       "--out", str(steps)]) == 0
    assert sweep.main(["check", "--dry-run"]) == 0
    assert sweep.main(["run", "--dry-run", "--table", str(steps),
                       "--log", str(logfile), "--no-tune"]) == 0
    assert logfile.exists()
    with logfile.open() as fh:
        rows = list(csv.DictReader(row for row in fh if not row.startswith("#")))
    assert any(row["phase"] == "record_start" for row in rows)
    assert any(row["phase"] == "complete" for row in rows)


def test_external_speed_table_bound(tmp_path):
    steps = tmp_path / "unsafe.csv"
    steps.write_text("rpm,wait_s,record_s\n4000,0,1\n")
    assert sweep.main(["run", "--dry-run", "--table", str(steps)]) == 1
