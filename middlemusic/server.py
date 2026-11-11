import argparse

from waitress import serve

from . import create_app


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Run the middleMusic server.")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind to")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    args = parser.parse_args(argv)
    serve(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
