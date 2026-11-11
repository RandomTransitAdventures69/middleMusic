from setuptools import find_packages, setup

setup(
    name="middlemusic",
    version="0.2.0",
    description="Self-hosted music server with Subsonic API and desktop client",
    packages=find_packages(),
    package_data={"middlemusic": ["static/*.html", "static/*.js", "static/*.css"]},
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=[
        "Flask>=3.1,<4",
        "Werkzeug>=3.1,<4",
        "mutagen>=1.47,<2",
        "imageio-ffmpeg>=0.5.1,<1",
        "cryptography>=44,<47",
        "waitress>=3,<4",
    ],
    extras_require={"client": ["PySide6>=6.8,<7"]},
    entry_points={
        "console_scripts": [
            "middlemusic-server=middlemusic.server:main",
            "middlemusic-client=middlemusic.desktop_client:main",
            "middlemusic-converter=middlemusic.converter_gui:main",
        ]
    },
    zip_safe=False,
)
