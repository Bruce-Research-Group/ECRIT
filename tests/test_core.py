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

from ui.core import devices
from ui.core.devices import (DeviceError, Printer, check_ports, describe_hat, describe_printer,
                             format_number, parse_cell_potential, parse_telemetry)
from ui.core.link import Link
from ui.core.plating import CSV_COLUMNS, REFERENCE_COLUMN, PlatingRun, describe_reference
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

    def test_cell_potential(self):
        self.assertEqual(parse_cell_potential("63.0012,3.712,3.700,0.91234"), 0.91234)
        self.assertEqual(parse_cell_potential("1,2,3,0.5,1.2,0.6,0.0,2.3,CV"), 0.5)  # format 1
        nan = parse_cell_potential("1,2,3,nan")
        self.assertTrue(nan is not None and nan != nan)
        for line in ("63.0012,3.712,3.700", "1,2,3,x", "Reset"):
            self.assertIsNone(parse_cell_potential(line), line)

    def test_describe_reference(self):
        self.assertEqual(describe_reference(-0.91234), "-0.9123 V")
        self.assertEqual(describe_reference(float("nan")), "no reading")
        self.assertIn("is the RE connected", describe_reference(-2.048))

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

    def test_remove_and_reorder_points(self):
        s = make_session()
        s.points[:] = [(1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
        s.move_point(3, 0)
        self.assertEqual(s.points, [(4.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)])
        s.move_point(1, 2)
        self.assertEqual(s.points, [(4.0, 0.0), (2.0, 0.0), (1.0, 0.0), (3.0, 0.0)])
        self.assertEqual(s.remove_point(1), (2.0, 0.0))
        self.assertEqual(s.points, [(4.0, 0.0), (1.0, 0.0), (3.0, 0.0)])
        for bad in (-1, 3):
            with self.assertRaises(IndexError):
                s.remove_point(bad)
            with self.assertRaises(IndexError):
                s.move_point(0, bad)
        self.assertEqual(len(s.points), 3)

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

    def test_reference_run(self):
        from ui.core.plot import load_run, save_plot
        s = ready_session()
        s.reference = True
        result, _ = self.run_it(s)
        self.assertTrue(result.completed, result.summary())
        sent = s.rig.hat.link.sent
        self.assertEqual(sent[:3], ["r", "t 3", "c 63"])
        self.assertEqual(sent[-1], "t 0")  # left on the plain format
        self.assertEqual(s.rig.hat.link.telemetry_format, 0)

        # RE - WE = 0.6 V + 63 mA * 5 ohm in the sim; the CSV has it negated.
        for smp in result.samples:
            self.assertAlmostEqual(smp.we_vs_re_V, -0.915, delta=0.01)
        rows = result.csv_path.read_text().splitlines()
        self.assertEqual(rows[0], ",".join(CSV_COLUMNS + (REFERENCE_COLUMN,)))
        self.assertEqual(rows.count(",,,,,"), 2)
        self.assertIn("reference_electrode True\n", result.log_path.read_text())

        samples, _, _ = load_run(result.csv_path)
        self.assertEqual([x.we_vs_re_V for x in samples], [x.we_vs_re_V for x in result.samples])
        save_plot(self.dir / "plot.png", samples, result.params.points, result.params.duration)
        self.assertTrue((self.dir / "plot.png").stat().st_size > 0)

    def test_plain_run_has_no_reference(self):
        from ui.core.plot import load_run
        s = ready_session(points=((10.0, 10.0),))
        result, _ = self.run_it(s)
        self.assertTrue(all(smp.we_vs_re_V is None for smp in result.samples))
        self.assertTrue(all(smp.we_vs_re_V is None for smp in load_run(result.csv_path)[0]))

    def test_reference_on_firmware_without_format_3(self):
        s = ready_session(points=((10.0, 10.0),), formats=(0, 1, 2))
        s.reference = True
        with self.assertLogs("ui.core.devices", "WARNING"):
            result, _ = self.run_it(s)
        self.assertTrue(result.completed, result.summary())
        self.assertEqual(s.rig.hat.link.sent[:4], ["r", "t 3", "t 1", "c 63"])
        self.assertAlmostEqual(result.samples[0].we_vs_re_V, -0.915, delta=0.01)

    def test_reference_needs_ecrit_hat_firmware(self):
        s = ready_session(points=((10.0, 10.0),), formats=())
        s.reference = True
        result, _ = self.run_it(s)
        self.assertIn("Flash ECRIT_HAT", result.error or "")
        self.assertFalse(any(line.startswith("c") for line in s.rig.hat.link.sent))

    def test_open_reference_reads_full_scale(self):
        s = ready_session(points=((10.0, 10.0),), reference_open=True)
        s.reference = True
        result, _ = self.run_it(s)
        self.assertIn("is the RE connected", describe_reference(result.samples[0].we_vs_re_V))


class ProbeTest(unittest.TestCase):
    SURFACE = 45.037

    def probe(self, start_z=48.0, surface_z=SURFACE, **settings):
        from ui.core.probe import BaselineProbe, ProbeSettings
        rig = sim_rig(speed_mm_s=200.0, home_s=0.05, surface_z=surface_z, quickstop_ok_s=0.05)
        session = Session(rig, Config())
        session.start()
        session.move_to(z=start_z)
        rig.printer.wait_for_moves()
        # Sweep at 5 mm/s by default to keep the tests short.
        return session, BaselineProbe(session, ProbeSettings(**{"settle": 0.0, "speed": 5.0, **settings}))

    def check_found(self, session, result):
        # The first fine step at or below the surface.
        self.assertGreater(result.z, self.SURFACE - 0.02)
        self.assertLessEqual(result.z, self.SURFACE)
        self.assertEqual(session.baseline_z, result.z)
        self.assertTrue(session.baseline_set)
        self.assertEqual(session.position["z"], round(result.z + 1, 3))  # lifted 1 mm
        self.assertEqual(session.rig.hat.link.sent[0], "z")
        self.assertEqual(session.rig.hat.link.sent.count("probe start"), 2)
        self.assertEqual(session.rig.hat.link.probe_state, "contact")

    def test_sweep_finds_surface(self):
        session, probe = self.probe()
        result = probe.run()
        self.check_found(session, result)
        # Stopped by M410 a little past the surface, not at the segment end.
        self.assertIn("M410", session.rig.printer.link.sent)
        self.assertLess(result.coarse_z, self.SURFACE + 0.01)
        self.assertGreater(result.coarse_z, self.SURFACE - 0.2)
        # The slow sweep feedrate is not left behind.
        self.assertEqual(session.rig.printer.link.sent[-3], "G1 F1500")

    def test_sweep_over_several_segments(self):
        session, probe = self.probe(start_z=50.0, segment=1.0, speed=5.0)
        result = probe.run()
        self.check_found(session, result)
        self.assertGreaterEqual(sum(1 for m in session.rig.printer.link.sent if m.endswith(" F300")), 4)

    def test_stepping_finds_surface(self):
        session, probe = self.probe(speed=0)
        result = probe.run()
        self.check_found(session, result)
        self.assertEqual(result.z, 45.02)
        self.assertEqual(result.coarse_z, 45.0)
        self.assertNotIn("M410", session.rig.printer.link.sent)
        lowest = min(z for _, _, z in session.rig.printer.link.moves if z is not None)
        self.assertGreaterEqual(lowest, self.SURFACE - 0.1)

    def test_waits_for_moves_in_progress(self):
        session, probe = self.probe(start_z=0.0)
        session.move_to(z=48.0)  # passes through the surface; not waited for
        self.check_found(session, probe.run())

    def test_coarse_only(self):
        session, probe = self.probe(speed=0, fine_step=0)
        self.assertEqual(probe.run().z, 45.0)

    def test_no_contact(self):
        from ui.core.probe import ProbeError
        for speed in (5.0, 0):
            session, probe = self.probe(surface_z=None, max_travel=1.0, speed=speed)
            with self.assertRaisesRegex(ProbeError, "No contact down to Z 47"):
                probe.run()
            self.assertEqual(session.position["z"], 47.0)
            self.assertFalse(session.baseline_set)
            self.assertNotEqual(session.rig.hat.link.probe_state, "armed")

    def test_cancel_stops_the_sweep(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(surface_z=None, speed=1.0)
        threading.Timer(0.6, probe.stop).start()
        with self.assertRaisesRegex(ProbeError, "cancelled"):
            probe.run()
        link = session.rig.printer.link
        self.assertIn("M410", link.sent)
        self.assertEqual(link.live(), link.position)  # standing still
        self.assertGreater(session.position["z"], 47.0)
        self.assertEqual(session.rig.hat.link.probe_state, "aborted")
        self.assertFalse(session.baseline_set)

    def test_firmware_abort_mid_sweep_stops_the_head(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(surface_z=None, speed=1.0)
        hat = session.rig.hat.link
        threading.Timer(0.6, lambda: hat._handle("probe stop")).start()  # as if the firmware gave up
        with self.assertRaisesRegex(ProbeError, "state=aborted"):
            probe.run()
        link = session.rig.printer.link
        self.assertIn("M410", link.sent)
        self.assertEqual(link.live(), link.position)
        self.assertGreater(session.position["z"], 47.0)

    def test_cancel_before_the_sweep_moves(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(surface_z=None, speed=1.0, settle=0.3)
        threading.Timer(0.15, probe.stop).start()  # during the first poll's settle
        with self.assertRaisesRegex(ProbeError, "cancelled"):
            probe.run()
        self.assertEqual(session.position["z"], 48.0)

    def test_cancel_while_stepping(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(surface_z=None, speed=0, settle=0.05)
        threading.Timer(0.3, probe.stop).start()
        with self.assertRaisesRegex(ProbeError, "cancelled"):
            probe.run()
        self.assertEqual(session.rig.hat.link.probe_state, "aborted")

    def test_failed_quickstop_is_caught(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(speed=1.0)
        link = session.rig.printer.link
        handle = link._handle
        link._handle = lambda text: link._push("ok") if text == "M410" else handle(text)
        with self.assertRaisesRegex(ProbeError, "M410 did not stop"):
            probe.run()
        self.assertFalse(session.baseline_set)

    def test_already_touching_after_backoff(self):
        from ui.core.probe import ProbeError
        session, probe = self.probe(surface_z=100.0)  # touching everywhere
        with self.assertRaisesRegex(ProbeError, "Still in contact"):
            probe.run()

    def test_refused_without_psu(self):
        from ui.core.probe import BaselineProbe, ProbeSettings
        rig = sim_rig(**FAST, psu=False)
        session = Session(rig, Config())
        session.start()
        with self.assertRaisesRegex(DeviceError, "PSU not Connected"):
            BaselineProbe(session, ProbeSettings(settle=0.0)).run()
        self.assertEqual(rig.printer.link.moves, [])

    def test_settings_check(self):
        from ui.core.probe import ProbeSettings
        ProbeSettings().check()
        for bad in (dict(step=0), dict(step=2), dict(fine_step=0.5), dict(backoff=0.01), dict(max_travel=0),
                    dict(speed=10), dict(speed=-1), dict(segment=0), dict(feedrate=0)):
            with self.assertRaises(ValueError, msg=bad):
                ProbeSettings(**bad).check()


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


class PortCheckTest(unittest.TestCase):
    def test_describe_sim_boards(self):
        rig = sim_rig(**FAST)
        self.assertEqual(describe_hat(rig.hat), "ECRIT-HAT answered, PSU: connected")
        self.assertEqual(describe_printer(rig.printer),
                         "Printer answered: Marlin 2.1.1.2, Electroplating Machine V1")
        self.assertEqual(describe_hat(sim_rig(psu=False).hat), "ECRIT-HAT answered, no PSU connected")

    def test_describe_real_m115(self):
        m115 = ("FIRMWARE_NAME:Marlin 2.1.1.2 (Apr 26 2024 16:09:15) SOURCE_CODE_URL:github.com/MarlinFirmware/Marlin "
                "PROTOCOL_VERSION:1.0 MACHINE_TYPE:Electroplating Machine V1 EXTRUDER_COUNT:1 UUID:cede2a2f")
        printer = Printer(_SilentLink([(0, m115), (0, "ok")]))
        self.assertEqual(describe_printer(printer), "Printer answered: Marlin 2.1.1.2, Electroplating Machine V1")

    def test_check_ports(self):
        rig = sim_rig(**FAST)
        boards = {"hat-port": rig.hat, "printer-port": rig.printer}

        def opener(kind):
            def open_(port):
                board = boards.get(port)
                if not isinstance(board, kind):
                    raise DeviceError(f"No {kind.__name__} answering on {port}")
                return board
            return open_

        saved = devices.open_hat, devices.open_printer
        devices.open_hat, devices.open_printer = opener(devices.Hat), opener(Printer)
        try:
            hat, printer = check_ports("hat-port", "printer-port")
            self.assertTrue(hat.ok and printer.ok, (hat, printer))
            hat, printer = check_ports("printer-port", "hat-port")
            self.assertFalse(hat.ok or printer.ok)
            self.assertIn("No Hat answering on printer-port", hat.detail)
            hat, printer = check_ports("hat-port", "")
            self.assertTrue(hat.ok)
            self.assertEqual(printer.detail, "No port selected")
            hat, printer = check_ports("hat-port", "hat-port")
            self.assertFalse(hat.ok or printer.ok)
        finally:
            devices.open_hat, devices.open_printer = saved


class OptionsTest(unittest.TestCase):
    def test_round_trip(self):
        path = Path(tempfile.mkdtemp()) / "options.json"
        self.assertEqual(Options.load(path).arduino_port, "")
        options = Options.load(path)
        options.arduino_port = "/dev/ttyACM0"
        options.save()
        self.assertEqual(Options.load(path).arduino_port, "/dev/ttyACM0")

    def test_probe_settings_from_config(self):
        from ui.core.probe import ProbeSettings
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text('{"travel_feedrate": 1200, "probe": {"speed": 0.5, "max_travel": 20, "bogus": 1}}')
        with self.assertLogs("ui.core.probe", "WARNING") as logged:
            settings = ProbeSettings.from_config(Config.load(path))
        self.assertIn("bogus", logged.output[0])
        self.assertEqual((settings.speed, settings.max_travel, settings.feedrate), (0.5, 20.0, 1200))
        self.assertEqual(settings.backoff, ProbeSettings().backoff)  # not given: default
        self.assertEqual(ProbeSettings.from_config(Config()), ProbeSettings())
        # The shipped config.json is valid.
        ProbeSettings.from_config(Config.load()).check()

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
            "home", "step 10", "jog z +", "jog z +", "jog z +", "baseline here", "jog z -", "baseline 20",
            "jog x 5", "point", "point",
            "jog x 5", "point", "points", "mode voltage", "voltage 2", "duration 0.2", "params",
            "start", "start -y", "pos", "bogus", "quit"])
        code, out = self.cli(["--sim", "--sim-speed", "5000", "shell", "--out", out_dir], script)
        self.assertIn("baseline Z 30", out)  # baseline here, at Z 30
        self.assertIn("baseline Z 20", out)
        self.assertIn("a point is already set at (5, 0)", out)
        self.assertIn("2: (10, 0)", out)  # numbered from 1, as in the GUI
        self.assertIn("use start -y in scripts", out)
        self.assertIn("completed. 2/2 point(s)", out)
        self.assertIn("unknown command 'bogus'", out)
        self.assertIn("stopping", out)
        self.assertEqual(code, 1)  # the bogus command
        self.assertEqual(len(list(Path(out_dir).glob("log_*.csv"))), 1)

    def test_shell_delete_and_reorder(self):
        script = "\n".join(["step 10", "point", "jog x +", "point", "jog x +", "point",
                             "reorder 3 1", "delete 2", "points", "delete 5"])
        code, out = self.cli(["--sim", "--sim-speed", "5000", "shell"], script)
        self.assertIn("1: (20, 0)\n2: (0, 0)\n3: (10, 0)", out)  # after reorder
        self.assertIn("removed (0, 0), 2 point(s) left", out)
        self.assertIn("1: (20, 0)\n2: (10, 0)", out)
        self.assertIn("error: there is no point 5 (2 set)", out)
        self.assertEqual(code, 1)

    def test_piped_shell_stops_at_first_error(self):
        code, out = self.cli(["--sim", "--sim-speed", "5000", "shell"], "move z=999\nmove z=10\npos\n")
        self.assertEqual(code, 1)
        self.assertNotIn("> move z=10", out)

    def test_piped_baseline_search_needs_y(self):
        code, out = self.cli(["--sim", "shell"], "baseline\npos\n")
        self.assertIn("use baseline -y in scripts", out)
        self.assertIn("> pos", out)  # not an error

    def test_run_command(self):
        out_dir = tempfile.mkdtemp()
        code, out = self.cli(["--sim", "--sim-speed", "5000", "run", "--point", "10,10", "--baseline", "40",
                              "--duration", "0.2", "--current", "5", "--out", out_dir, "-y"])
        self.assertEqual(code, 0, out)
        self.assertIn("5 mA constant current", out)
        self.assertIn("reference electrode off", out)

    def test_run_command_with_reference(self):
        out_dir = tempfile.mkdtemp()
        code, out = self.cli(["--sim", "--sim-speed", "5000", "run", "--point", "10,10", "--baseline", "40",
                              "--duration", "1.2", "--current", "5", "--ref", "--out", out_dir, "-y"])
        self.assertEqual(code, 0, out)
        self.assertIn("reference electrode on", out)
        self.assertIn("WE-RE=-0.6", out)
        csv_path = next(Path(out_dir).glob("log_*.csv"))
        self.assertTrue(csv_path.read_text().startswith(",".join(CSV_COLUMNS + (REFERENCE_COLUMN,))))

    def test_shell_ref(self):
        code, out = self.cli(["--sim", "shell"], "ref\nref on\nref off\nref maybe\n")
        self.assertIn("reference electrode off", out)
        self.assertIn("reference electrode on", out)
        self.assertEqual(code, 1)  # ref maybe

    def test_run_refuses_bad_params(self):
        with self.assertRaises(SystemExit):
            self.cli(["--sim", "run", "--point", "999,1", "--baseline", "40", "-y"])


if __name__ == "__main__":
    unittest.main()
