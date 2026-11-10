import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from middlemusic import gui


class GuiTests(unittest.TestCase):
    def test_gui_script_runs_without_package_context(self):
        gui_script = Path(__file__).resolve().parents[1] / "middlemusic" / "gui.py"
        runner = """
import runpy
import sys
from unittest.mock import Mock, patch
from werkzeug import serving

server = Mock()
server.server_port = 12345
server.serve_forever.side_effect = KeyboardInterrupt
timer = Mock()
with patch.object(serving, "make_server", return_value=server), patch(
    "threading.Timer", return_value=timer
):
    runpy.run_path(sys.argv[1], run_name="__main__")
"""
        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [sys.executable, "-c", runner, str(gui_script)],
                cwd=working_directory,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_keyboard_interrupt_closes_server_without_blocking_shutdown(self):
        server = Mock()
        server.server_port = 12345
        server.serve_forever.side_effect = KeyboardInterrupt
        timer = Mock()
        timer_factory = Mock(return_value=timer)

        with ExitStack() as stack:
            stack.enter_context(patch.object(gui, "create_app"))
            stack.enter_context(patch.object(gui, "make_server", return_value=server))
            stack.enter_context(patch.object(gui.threading, "Timer", timer_factory))
            gui.main(open_converter=True)

        self.assertTrue(timer.daemon)
        timer_factory.assert_called_once_with(
            0.5,
            gui._open_browser,
            args=("http://127.0.0.1:12345/?view=converter",),
        )
        timer.start.assert_called_once()
        timer.cancel.assert_called_once()
        server.server_close.assert_called_once()
        server.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
