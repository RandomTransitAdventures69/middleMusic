import threading
import webbrowser

from werkzeug.serving import make_server

from . import create_app


def main() -> None:
    server = make_server("127.0.0.1", 0, create_app(), threaded=True)
    address = f"http://127.0.0.1:{server.server_port}"
    threading.Timer(0.5, webbrowser.open, args=(address,)).start()
    print(f"middleMusic is running at {address}. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
