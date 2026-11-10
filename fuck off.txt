# GitHub Copilot Project Prompt — Self-Hosted Music Server

## Project Overview

Build a modern, open-source, self-hosted music streaming application inspired by Navidrome, but with a major focus on ease of installation, setup, configuration, and everyday use.

The goal is to make self-hosted music accessible to people who want to stream their personal music libraries without needing extensive technical knowledge.

The application should be lightweight, reliable, easy to maintain, and suitable for running on:
- Windows PCs
- Linux servers
- Raspberry Pi devices
- Docker containers
- Small home servers and NAS systems

The application should have a clean, modern user interface inspired by contemporary applications such as Spotify, Apple Music, and Jellyfin.

Do not simply recreate another existing music application. Develop an original product with its own identity.

## Core Philosophy

The most important feature of this project is simplicity.

Users should not need to:
- Read hundreds of pages of documentation.
- Manually edit configuration files to get started.
- Understand complicated networking concepts.
- Install multiple dependencies manually.
- Spend hours configuring a music server.

The project should aim to reduce the installation and user documentation burden from approximately 100+ pages to around 10 pages.

Documentation should explain the application clearly, but the application itself should handle as much configuration as possible.

Prioritize working features, reliability, and simplicity over unnecessary complexity.

## Installation Experience

The application should support multiple installation methods.

### Docker

Provide a Docker image with:
- Sensible default configuration.
- Persistent configuration and database storage.
- Music library mounting.
- Simple startup instructions.
- Straightforward upgrades.
- Minimal required environment variables.

The application should be usable with a simple Docker Compose configuration.

### Windows

Plan for a Windows installer that:
- Installs the application.
- Configures required components automatically.
- Allows the user to select a music directory.
- Starts the music server.
- Opens the web interface.

### Linux

Provide a straightforward Linux installation method.

Avoid requiring users to compile the application from source.

### Portable Installation

Where practical, support running the application without a traditional installation process.

## First-Run Setup Wizard

On the first launch, the application should display a setup wizard.

The wizard should guide the user through:

1. Creating an administrator account.
2. Selecting a music library directory.
3. Configuring the server name.
4. Scanning the music library.
5. Completing setup and opening the music player.

The wizard should explain what each setting does in plain English.

Do not expose unnecessary technical settings during initial setup.

Advanced configuration can be available in the settings interface.

## Core Music Features

Implement the following features as the initial product scope.

### Music Library

- Automatically scan music directories.
- Support common audio formats, including MP3, FLAC, AAC, Ogg Vorbis, and WAV.
- Read embedded metadata and album artwork.
- Browse by artist, album, song, and genre.
- Search the entire music library.
- Handle missing or incomplete metadata gracefully.
- Allow users to rescan their library.
- Avoid duplicate entries when rescanning.

### Music Player

Build a functional web-based music player with:

- Play and pause.
- Previous and next track.
- Seek bar.
- Volume control.
- Shuffle.
- Repeat.
- Queue management.
- Album artwork.
- Current track information.
- Keyboard controls where appropriate.

The player should work on desktop and mobile browsers.

### Playlists

Support:
- Creating playlists.
- Editing playlists.
- Removing tracks.
- Reordering tracks.
- Saving playlists.
- Playing playlists.

### Favorites

Users should be able to favorite songs and albums.

Favorites should persist between sessions.

## User Interface

Create a polished, modern, responsive interface.

The design should prioritize usability over visual gimmicks.

### Design Principles

- Clean and modern.
- Consistent spacing.
- Clear typography.
- Boxy, organized layouts.
- Responsive design.
- Dark and light themes.
- Accessible contrast.
- Simple navigation.
- Minimal unnecessary animations.

Avoid:
- Generic unfinished dashboards.
- Excessive gradients.
- Overly complicated navigation.
- Excessive empty space.
- Unnecessary technical terminology.
- Interfaces that look like raw administration panels.

### Main Navigation

Include:

- Home
- Artists
- Albums
- Songs
- Playlists
- Favorites
- Search
- Settings

The music player should remain accessible throughout the application.

### Home Page

The home page should include:

- Recently played.
- Recently added.
- Favorite albums.
- Suggested library browsing sections.

Do not implement artificial recommendations that require external services.

## Settings

Create an understandable settings interface.

Settings should include:

### General

- Server name.
- Theme.
- Language, if supported.
- Basic application preferences.

### Music Library

- Current music directories.
- Add or remove music directories.
- Scan library.
- Scan status.
- Library statistics.

### Server

- Server status.
- Application version.
- Basic network configuration.
- Storage information.

### Administration

- User management, if multi-user functionality is implemented.
- Basic server maintenance.
- Application logs.

Technical settings should be explained in plain English.

## Architecture

Before implementing the application:

1. Inspect the existing repository.
2. Identify the current programming language, framework, and project structure.
3. Reuse existing working components where possible.
4. Identify missing functionality.
5. Propose a practical architecture.
6. Implement the application incrementally.

Do not replace the entire project unnecessarily.

Keep the architecture modular and maintainable.

Separate concerns such as:

- Music library scanning.
- Metadata extraction.
- Audio streaming.
- Authentication.
- Database operations.
- API endpoints.
- Frontend components.
- Configuration.
- Logging.

Choose technologies that are lightweight, reliable, and appropriate for self-hosting.

Avoid introducing unnecessary dependencies.

Do not require users to compile complex dependencies manually.

## Security and Reliability

The application must:

- Store passwords securely using an appropriate password-hashing algorithm.
- Validate user input.
- Restrict access to administrative functions.
- Prevent directory traversal.
- Avoid exposing arbitrary files from the server.
- Handle malformed music metadata safely.
- Provide useful error messages.
- Avoid logging passwords or other secrets.

Do not assume the application will only be used on localhost.

## Documentation

Create concise, useful documentation.

The documentation should aim to cover the entire project in approximately 10 pages or fewer, excluding generated API references if necessary.

Include:

- Installation.
- First-run setup.
- Music library configuration.
- Basic usage.
- Docker deployment.
- Windows deployment.
- Linux deployment.
- Troubleshooting.
- Backup and restoration.
- Development and contribution instructions.

Avoid documenting every individual interface element when the interface itself can explain it.

## Development Instructions

Implement the project in manageable stages.

### Stage 1: Foundation

- Establish the application structure.
- Implement the backend.
- Implement the frontend.
- Establish database functionality.
- Create the initial setup wizard.

### Stage 2: Music Library

- Implement scanning.
- Implement metadata extraction.
- Implement album and artist browsing.
- Implement search.

### Stage 3: Music Playback

- Implement audio streaming.
- Implement the player interface.
- Implement the queue.
- Implement playlists and favorites.

### Stage 4: Installation

- Implement Docker deployment.
- Improve Windows installation.
- Improve Linux installation.
- Test the first-run experience.

### Stage 5: Polish

- Improve responsive design.
- Fix bugs.
- Improve error handling.
- Write documentation.
- Add automated tests.

Do not attempt to implement every stage in one enormous code generation operation.

## Important Instructions for Copilot

- Inspect the repository before making changes.
- Do not assume files or features exist.
- Do not create placeholder functionality and claim it works.
- Do not leave broken imports or missing dependencies.
- Do not generate HTML without the corresponding CSS and JavaScript.
- Do not unnecessarily rewrite working code.
- Keep the project compatible with its intended platforms.
- Explain significant architectural decisions.
- Test changes when practical.
- Prioritize a functional application over an impressive-looking mockup.

If a feature is too large to implement immediately, create a clear plan and implement the foundational functionality first.

The final product should feel like a complete, approachable self-hosted music application rather than an unfinished developer project.

**Primary objective: Make self-hosted music streaming so easy that a user can install the application, select their music folder, and start listening without reading a complicated manual.**
