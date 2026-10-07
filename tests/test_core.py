"""Core and CLI tests against the simulated boards. No hardware needed.

    python3 -m unittest discover tests      (from the repository root)
"""

import contextlib
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ui.core.devices import DeviceError, Printer, format_number, parse_telemetry
from ui.core.link import Link
from ui.core.plating import CSV_COLUMNS, PlatingRun
from ui.core.session import Session
from ui.core.settings import Config, Options
from ui.core.sim import sim_rig

FAST = dict(speed_mm_s=5000.0, home_s=0.05)


def make_session(**sim):
    rig = sim_rig(**{**FAST, **sim})
    session = Session(rig, Config())
    session.start()
    return session


def ready_session(points=((10.0, 20.0), (30.0, 20.0)), duration=0.3, **sim):
    session = make_session(**sim)
    session.move_to(z=50)
    session.set_baseline()
    for x, y in points:
        session.move_to(x=x, y=y)
        session.add_point()
    session.duration = duration
    return session


class ParsingTest(unittest.TestCase):
    def test_telemetry(self):
        self.assertEqual(parse_telemetry("63.0012,3.712,3.700"), (63.0012, 3.712, 3.7))
        self.assertEqual(parse_telemetry("1,2,3,4,5,CV"), (1.0, 2.0, 3.0))
        nan = parse_telemetry("nan,1.000,1.000")
        self.assertTrue(nan is not None and nan[0] != nan[0])
        for line in ("Reset", "Hold Current, target = 5 mA", "TRIP ocp at 9", ">current:1,voltage:2,x:3", "1,2"):
            self.assertIsNone(parse_telemetry(line), line)

    def test_format_number(self):
        self.assertEqual(format_number(12.5), "12.5")
        self.assertEqual(format_number(3.0), "3")
        self.assertEqual(format_number(0.1 + 0.2), "0.3")
        self.assertEqual(format_number(-0.0001), "0")


class SessionTest(unittest.TestCase):
    def test_jog_clamps_and_rounds(self):
        s = make_session()
        s.jog("x", 0.1)
        s.jog("x", 0.2)
        self.assertEqual(s.position["x"], 0.3)
        s.jog("x", -5)
        self.assertEqual(s.position["x"], 0.0)
        s.jog("z", 1000)
        self.assertEqual(s.position["z"], s.config.z_limit)
        self.assertEqual(s.rig.printer.link.moves[-1], (None, None, 200.0))

    def test_start_reads_position_from_printer(self):
        rig = sim_rig(**FAST)
        rig.printer.link.position = {"X": 12.0, "Y": 34.0, "Z": 56.0}
        s = Session(rig, Config())
        s.start()
        self.assertEqual(s.position, {"x": 12.0, "y": 34.0, "z": 56.0})

    def test_move_outside_limits_is_refused(self):
        s = make_session()
        with self.assertRaises(ValueError):
            s.move_to(x=-1)
        with self.assertRaises(ValueError):
            s.move_to(z=201)
        self.assertEqual(s.rig.printer.link.moves, [])

    def test_points(self):
        s = make_session()
        self.assertTrue(s.add_point())
        self.assertFalse(s.add_point())
        s.jog("x", 5)
        self.assertTrue(s.add_point())
        self.assertEqual(s.points, [(0.0, 0.0), (5.0, 0.0)])
        self.assertEqual(s.undo_point(), (5.0, 0.0))
        self.assertEqual(s.undo_point(), (0.0, 0.0))
        self.assertIsNone(s.undo_point())

    def test_run_params_check(self):
        s = make_session()
        with self.assertRaisesRegex(ValueError, "geometric area"):
            s.run_params()
        s.add_point()
        s.baseline_z = 199
        with self.assertRaisesRegex(ValueError, "Plating height"):
            s.run_params()
        s.baseline_z = 50
        s.duration = 0
        with self.assertRaisesRegex(ValueError, "duration"):
            s.run_params()


class RunTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def run_it(self, session, stop_after=None):
        events = []
        run = PlatingRun(session.rig, session.run_params(), work_dir=self.dir,
                         on_event=lambda kind, payload: events.append((kind, payload)))
        if stop_after is not None:
            threading.Timer(stop_after, run.stop).start()
        return run.run(), events

    def test_complete_run(self):
        s = ready_session()
        result, events = self.run_it(s)
        self.assertTrue(result.completed, result.summary())
        self.assertEqual(result.points_done, 2)
        self.assertGreater(len(result.samples), 6)
        self.assertEqual({smp.point for smp in result.samples}, {0, 1})

        rows = result.csv_path.read_text().splitlines()
        self.assertEqual(rows[0], ",".join(CSV_COLUMNS))
        self.assertEqual(rows.count(",,,,"), 2)  # one spacer per point
        self.assertEqual(len(rows), 1 + 2 + len(result.samples))
        log = result.log_path.read_text()
        self.assertIn("points 2\n", log)
        self.assertIn("x: 10.000, y: 20.000", log)

        p = result.params
        moves = s.rig.printer.link.moves[-9:]
        self.assertEqual(moves, [
            (None, None, p.travel_z), (None, None, p.plate_z + 2),
            (10.0, 20.0, None), (None, None, p.plate_z), (None, None, p.plate_z + 2),
            (30.0, 20.0, None), (None, None, p.plate_z), (None, None, p.plate_z + 2),
            (None, None, p.travel_z)])
        sent = s.rig.hat.link.sent
        self.assertEqual(sent[:3], ["r", "t 0", "c 63"])
        self.assertEqual(sent.count("c 63"), 2)
        self.assertEqual(sent[-1], "f")
        self.assertFalse(s.rig.hat.link.active)
        self.assertEqual(s.rig.printer.link.lcd, "Done")
        self.assertEqual(events[-1], ("finished", result))

    def test_voltage_mode(self):
        s = ready_session(points=((10.0, 10.0),))
        s.current_mode = False
        s.target_voltage = 2.5
        result, _ = self.run_it(s)
        self.assertTrue(result.completed)
        self.assertIn("v 2.5", s.rig.hat.link.sent)

    def test_trip_stops_without_moving(self):
        s = ready_session(duration=2.0, trip_after=0.3)
        result, _ = self.run_it(s)
        self.assertIn("TRIP ocp", result.stopped or "")
        self.assertEqual(result.points_done, 1)
        # Stopped at plating height: no lift, no second point.
        self.assertEqual(s.rig.printer.link.moves[-1], (None, None, result.params.plate_z))
        self.assertFalse(s.rig.hat.link.active)

    def test_cancel(self):
        s = ready_session(duration=5.0)
        started = time.monotonic()
        result, _ = self.run_it(s, stop_after=0.5)
        self.assertEqual(result.stopped, "cancelled")
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertFalse(s.rig.hat.link.active)

    def test_refused_output_is_an_error(self):
        s = ready_session(psu=False)
        result, _ = self.run_it(s)
        self.assertIn("PSU not Connected", result.error or "")
        self.assertEqual(result.samples, [])
        self.assertEqual(result.points_done, 0)

    def test_save_as_and_reload(self):
        from ui.core.plot import load_run
        s = ready_session()
        result, _ = self.run_it(s)
        target = self.dir / "saved" / "mine.csv"
        result.save_as(target)
        self.assertEqual(result.csv_path, target)
        self.assertTrue(target.with_suffix(".txt").exists())
        samples, points, duration = load_run(target)
        self.assertEqual(len(samples), len(result.samples))
        self.assertEqual(points, [(10.0, 20.0), (30.0, 20.0)])
        self.assertEqual(duration, 0.3)


class _SilentLink(Link):
    port = "silent"

    def __init__(self, lines=()):
        self.lines = list(lines)

    def write_line(self, text):
        pass

    def read_line(self, timeout):
        if self.lines:
            delay, line = self.lines.pop(0)
            time.sleep(delay)
            return line
        time.sleep(timeout)
        return None

    def discard_input(self):
        pass

    def close(self):
        pass


class PrinterTest(unittest.TestCase):
    def test_timeout(self):
        with self.assertRaises(DeviceError):
            Printer(_SilentLink()).send("G1 X1", timeout=0.2)

    def test_busy_extends_timeout(self):
        link = _SilentLink([(0.15, "echo:busy: processing"), (0.15, "echo:busy: processing"), (0.15, "ok")])
        self.assertEqual(Printer(link).send("G28", timeout=0.25), [])

    def test_restart_is_an_error(self):
        with self.assertRaisesRegex(DeviceError, "restarted"):
            Printer(_SilentLink([(0, "start")])).send("M114")


class OptionsTest(unittest.TestCase):
    def test_round_trip(self):
        path = Path(tempfile.mkdtemp()) / "options.json"
        self.assertEqual(Options.load(path).arduino_port, "")
        options = Options.load(path)
        options.arduino_port = "/dev/ttyACM0"
        options.save()
        self.assertEqual(Options.load(path).arduino_port, "/dev/ttyACM0")

    def test_config_ignores_unknown_keys(self):
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text('{"duration": 5, "inc_r": 2}')
        self.assertEqual(Config.load(path).duration, 5)


class CliTest(unittest.TestCase):
    def cli(self, argv, stdin=""):
        from ui import cli
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out):
                code = cli.main(argv)
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue()

    def test_shell_script(self):
        out_dir = tempfile.mkdtemp()
        script = "\n".join([
            "home", "step 10", "jog z +", "jog z +", "baseline", "jog x 5", "point", "point",
            "jog x 5", "point", "points", "mode voltage", "voltage 2", "duration 0.2", "params",
            "start", "start -y", "pos", "bogus", "quit"])
        code, out = self.cli(["--sim", "--sim-speed", "5000", "shell", "--out", out_dir], script)
        self.assertIn("baseline Z 20", out)
        self.assertIn("a point is already set at (5, 0)", out)
        self.assertIn("1: (10, 0)", out)
        self.assertIn("use start -y in scripts", out)
        self.assertIn("completed. 2/2 point(s)", out)
        self.assertIn("unknown command 'bogus'", out)
        self.assertEqual(code, 1)  # the bogus command
        self.assertEqual(len(list(Path(out_dir).glob("log_*.csv"))), 1)

    def test_run_command(self):
        out_dir = tempfile.mkdtemp()
        code, out = self.cli(["--sim", "--sim-speed", "5000", "run", "--point", "10,10", "--baseline", "40",
                              "--duration", "0.2", "--current", "5", "--out", out_dir, "-y"])
        self.assertEqual(code, 0, out)
        self.assertIn("5 mA constant current", out)

    def test_run_refuses_bad_params(self):
        with self.assertRaises(SystemExit):
            self.cli(["--sim", "run", "--point", "999,1", "--baseline", "40", "-y"])


if __name__ == "__main__":
    unittest.main()
