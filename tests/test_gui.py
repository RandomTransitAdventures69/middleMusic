import unittest
from unittest.mock import Mock, patch

from middlemusic import gui


class GuiTests(unittest.TestCase):
    def test_keyboard_interrupt_closes_server_without_blocking_shutdown(self):
        server = Mock()
        server.server_port = 12345
        server.serve_forever.side_effect = KeyboardInterrupt
        timer = Mock()

        with (
            patch.object(gui, "create_app"),
            patch.object(gui, "make_server", return_value=server),
            patch.object(gui.threading, "Timer", return_value=timer),
        ):
            gui.main()

        self.assertTrue(timer.daemon)
        timer.start.assert_called_once()
        timer.cancel.assert_called_once()
        server.server_close.assert_called_once()
        server.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
