import sys
import threading
import webbrowser

from werkzeug.serving import make_server

from . import create_app


def _open_browser(address: str) -> None:
    try:
        opened = webbrowser.open(address)
    except (OSError, webbrowser.Error) as error:
        print(
            f"Could not open a browser: {error}. Visit {address} manually.",
            file=sys.stderr,
        )
        return
    if not opened:
        print(f"Could not open a browser. Visit {address} manually.", file=sys.stderr)


def main() -> None:
    server = make_server("127.0.0.1", 0, create_app(), threaded=True)
    address = f"http://127.0.0.1:{server.server_port}"
    browser_timer = threading.Timer(0.5, _open_browser, args=(address,))
    browser_timer.daemon = True
    browser_timer.start()
    print(f"middleMusic is running at {address}. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down middleMusic.")
    finally:
        browser_timer.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
