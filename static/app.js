const state = {
  view: 'home',
  tracks: [],
  playlists: [],
  favorites: { tracks: [], albums: [] },
  session: { logged_in: false },
  currentTrack: null,
  queue: [],
  index: 0,
  shuffle: false,
  repeat: false,
};

const audio = document.getElementById('audio-player');
const elements = {
  serverName: document.getElementById('server-name'),
  setupPanel: document.getElementById('setup-panel'),
  loginPanel: document.getElementById('login-panel'),
  logoutButton: document.getElementById('logout-button'),
  themeToggle: document.getElementById('theme-toggle'),
  homeContent: document.getElementById('home-content'),
  artistsContent: document.getElementById('artists-content'),
  albumsContent: document.getElementById('albums-content'),
  songsContent: document.getElementById('songs-content'),
  playlistsContent: document.getElementById('playlists-content'),
  favoritesContent: document.getElementById('favorites-content'),
  searchContent: document.getElementById('search-content'),
  settingsContent: document.getElementById('settings-content'),
  searchInput: document.getElementById('search-input'),
  globalSearchInput: document.getElementById('global-search-input'),
  trackTitle: document.getElementById('track-title'),
  trackArtist: document.getElementById('track-artist'),
  trackAlbum: document.getElementById('track-album'),
  artwork: document.getElementById('artwork'),
  seekSlider: document.getElementById('seek-slider'),
  volumeSlider: document.getElementById('volume-slider'),
  playButton: document.getElementById('play-button'),
  previousButton: document.getElementById('previous-button'),
  nextButton: document.getElementById('next-button'),
  setupForm: document.getElementById('setup-form'),
  loginForm: document.getElementById('login-form'),
  scanLibraryButton: document.getElementById('scan-library-button'),
  newPlaylistButton: document.getElementById('new-playlist-button'),
  shuffleButton: document.getElementById('shuffle-button'),
  repeatButton: document.getElementById('repeat-button'),
};

function renderView(view) {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === view);
  });
  document.querySelectorAll('.view-panel').forEach((panel) => {
    panel.classList.toggle('hidden', panel.id !== `view-${view}`);
  });
  state.view = view;
}

function setTheme(theme) {
  document.body.classList.toggle('dark', theme === 'dark');
  localStorage.setItem('middlemusic-theme', theme);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || 'Request failed');
  }
  return payload;
}

function updateSessionUI() {
  const loggedIn = state.session.logged_in;
  elements.loginPanel.classList.toggle('hidden', loggedIn);
  elements.logoutButton.classList.toggle('hidden', !loggedIn);
  if (!loggedIn) {
    renderView('home');
  }
}

async function loadSession() {
  const setupStatus = await fetchJson('/api/setup/status');
  const setupRequired = setupStatus.requires_setup;
  elements.setupPanel.classList.toggle('hidden', !setupStatus.requires_setup);
  elements.serverName.textContent = setupStatus.server_name;
  document.getElementById('setup-library').value = setupStatus.library_path;
  document.getElementById('setup-server-name').value = setupStatus.server_name;

  if (setupRequired) {
    state.session.logged_in = false;
    updateSessionUI();
    return;
  }

  try {
    const sessionData = await fetchJson('/api/session');
    state.session = sessionData;
    updateSessionUI();
    if (sessionData.logged_in) {
      await Promise.all([loadHome(), loadArtists(), loadAlbums(), loadTracks(), loadPlaylists(), loadFavorites(), loadSettings()]);
    } else {
      elements.loginPanel.classList.remove('hidden');
    }
  } catch (error) {
    console.error(error);
  }
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${mins}:${secs}`;
}

function buildTrackRow(track, showPlay = true, extra = '') {
  const favorite = state.favorites.tracks.includes(String(track.id));
  return `
    <div class="track-item" data-id="${track.id}">
      <div class="list-art">
        ${track.artwork_url ? `<img src="${escapeHtml(track.artwork_url)}" alt="${escapeHtml(track.title)}" />` : '<div class="placeholder-art"></div>'}
      </div>
      <div class="track-meta">
        <div class="track-title">${escapeHtml(track.title || 'Untitled track')}</div>
        <div class="track-subtitle">${escapeHtml(track.artist || 'Unknown Artist')} • ${escapeHtml(track.album || 'Unknown Album')}</div>
      </div>
      <div class="track-actions">${extra}</div>
      ${showPlay ? `<button class="primary-button" data-action="play" data-track-id="${track.id}" type="button">Play</button>` : ''}
      ${showPlay ? `<button class="secondary-button" data-action="queue" data-track-id="${track.id}" type="button">Queue</button>` : ''}
      <button class="secondary-button" data-action="favorite" data-media-type="track" data-media-key="${track.id}" type="button">${favorite ? '★' : '☆'}</button>
    </div>
  `;
}

function renderTracks(list) {
  state.tracks = list;
  elements.songsContent.innerHTML = list.map((track) => buildTrackRow(track)).join('');
  elements.searchContent.innerHTML = list.map((track) => buildTrackRow(track)).join('');
}

function renderHome(data) {
  const recent = data.recently_added || [];
  const featured = data.favorite_albums || [];
  const cards = [...recent, ...featured].slice(0, 12).map((item) => {
    const isTrack = item.title;
    const art = item.artwork_url ? `<img src="${escapeHtml(item.artwork_url)}" alt="${escapeHtml(item.title || item.album)}" />` : '<div class="placeholder-art"></div>';
    return `
      <div class="card">
        <div class="card-art">${art}</div>
        <div class="track-title">${escapeHtml(isTrack ? item.title : item.album)}</div>
        <div class="track-subtitle">${escapeHtml(item.artist)}</div>
      </div>
    `;
  }).join('');
  elements.homeContent.innerHTML = cards || '<p>No music in the library yet. Scan your folder to get started.</p>';
}

async function loadHome() {
  const data = await fetchJson('/api/home');
  renderHome(data);
}

async function loadArtists() {
  const response = await fetchJson('/api/artists');
  elements.artistsContent.innerHTML = (response.artists || []).map((artist) => `
    <div class="card">
      <div class="card-art"><div class="placeholder-art"></div></div>
      <div class="track-title">${escapeHtml(artist.artist || 'Unknown Artist')}</div>
      <div class="track-subtitle">${artist.track_count || 0} tracks</div>
    </div>
  `).join('');
}

async function loadAlbums() {
  const response = await fetchJson('/api/albums');
  elements.albumsContent.innerHTML = (response.albums || []).map((album) => `
    <div class="card">
      <div class="card-art"><div class="placeholder-art"></div></div>
      <div class="track-title">${escapeHtml(album.album || 'Unknown Album')}</div>
      <div class="track-subtitle">${escapeHtml(album.artist || 'Unknown Artist')} • ${album.track_count || 0} songs</div>
    </div>
  `).join('');
}

async function loadTracks(query = '') {
  const response = await fetchJson(`/api/tracks?q=${encodeURIComponent(query)}`);
  state.tracks = response.tracks || [];
  renderTracks(state.tracks);
}

async function loadPlaylists() {
  const response = await fetchJson('/api/playlists');
  state.playlists = response.playlists || [];
  elements.playlistsContent.innerHTML = state.playlists.map((playlist) => `
    <div class="card">
      <div class="card-art"><div class="placeholder-art"></div></div>
      <div class="track-title">${escapeHtml(playlist.name)}</div>
      <div class="track-subtitle">${playlist.tracks?.length || 0} tracks</div>
      <button class="secondary-button" data-action="playlist-add" data-playlist-id="${playlist.id}" type="button">Add current track</button>
    </div>
  `).join('');
}

async function loadFavorites() {
  const response = await fetchJson('/api/favorites');
  state.favorites = response || { tracks: [], albums: [] };
  elements.favoritesContent.innerHTML = [...(response.tracks || [])].map((track) => buildTrackRow(track, true)).join('') || '<p>No favorites yet.</p>';
  if (response.albums && response.albums.length) {
    elements.favoritesContent.innerHTML += `<div class="card"><div class="track-title">Favorite albums</div>${response.albums.map((album) => `<div class="track-subtitle">${escapeHtml(album)}</div>`).join('')}</div>`;
  }
}

async function loadSettings() {
  const stats = await fetchJson('/api/library/stats');
  elements.settingsContent.innerHTML = `
    <div class="settings-card">
      <div><strong>Server name</strong><div>${escapeHtml(stats.server_name || 'middleMusic')}</div></div>
      <div><strong>Library path</strong><div>${escapeHtml(stats.library_path || 'Not configured')}</div></div>
      <div><strong>Tracks</strong><div>${stats.tracks || 0}</div></div>
      <div><strong>Artists</strong><div>${stats.artists || 0}</div></div>
      <div><strong>Albums</strong><div>${stats.albums || 0}</div></div>
    </div>
  `;
}

async function handleSetup(event) {
  event.preventDefault();
  const payload = {
    username: document.getElementById('setup-username').value,
    password: document.getElementById('setup-password').value,
    library_path: document.getElementById('setup-library').value,
    server_name: document.getElementById('setup-server-name').value,
  };
  try {
    await fetchJson('/api/setup', { method: 'POST', body: JSON.stringify(payload) });
    await loadSession();
  } catch (error) {
    alert(error.message);
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById('login-username').value;
  const password = document.getElementById('login-password').value;
  try {
    await fetchJson('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    state.session.logged_in = true;
    updateSessionUI();
    await Promise.all([loadHome(), loadArtists(), loadAlbums(), loadTracks(), loadPlaylists(), loadFavorites(), loadSettings()]);
  } catch (error) {
    alert(error.message);
  }
}

async function handleScanLibrary() {
  elements.scanLibraryButton.disabled = true;
  elements.scanLibraryButton.textContent = 'Scanning…';
  try {
    await fetchJson('/api/library/scan', { method: 'POST' });
    await Promise.all([loadHome(), loadArtists(), loadAlbums(), loadTracks(), loadSettings()]);
  } catch (error) {
    alert(error.message);
  } finally {
    elements.scanLibraryButton.disabled = false;
    elements.scanLibraryButton.textContent = 'Scan library';
  }
}

async function handleLogout() {
  await fetchJson('/api/logout', { method: 'POST' });
  state.session = { logged_in: false };
  updateSessionUI();
  elements.loginPanel.classList.remove('hidden');
  elements.loginForm.reset();
}

function setPlayback(track) {
  state.currentTrack = track;
  const audioUrl = `/api/stream/${track.id}`;
  audio.src = audioUrl;
  elements.trackTitle.textContent = track.title || 'Untitled track';
  elements.trackArtist.textContent = track.artist || 'Unknown Artist';
  elements.trackAlbum.textContent = track.album || '';
  elements.artwork.replaceChildren();
  elements.artwork.classList.toggle('placeholder-art', !track.artwork_url);
  if (track.artwork_url) {
    const cover = document.createElement('img');
    cover.src = track.artwork_url;
    cover.alt = `${track.album || 'Album'} cover`;
    elements.artwork.append(cover);
  }
  document.title = `${track.title || 'Now playing'} — middleMusic`;
  updateMediaMetadata(track);
  audio.play().catch((error) => console.error('Unable to play track:', error));
  elements.playButton.textContent = 'Pause';
}

function updateMediaMetadata(track) {
  if (!('mediaSession' in navigator) || !('MediaMetadata' in window)) return;
  const artwork = track.artwork_url
    ? [{ src: new URL(track.artwork_url, window.location.href).href }]
    : [];
  navigator.mediaSession.metadata = new window.MediaMetadata({
    title: track.title || 'Untitled track',
    artist: track.artist || 'Unknown Artist',
    album: track.album || 'Unknown Album',
    artwork,
  });
}

function setMediaPlaybackState(playing) {
  if ('mediaSession' in navigator) {
    navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
  }
}

function registerMediaActions() {
  if (!('mediaSession' in navigator)) return;
  const handlers = {
    play: () => audio.play(),
    pause: () => audio.pause(),
    previoustrack: () => elements.previousButton.click(),
    nexttrack: () => elements.nextButton.click(),
    seekto: (details) => {
      if (Number.isFinite(details.seekTime)) audio.currentTime = details.seekTime;
    },
    seekbackward: (details) => {
      audio.currentTime = Math.max(0, audio.currentTime - (details.seekOffset || 10));
    },
    seekforward: (details) => {
      audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + (details.seekOffset || 10));
    },
  };
  for (const [action, handler] of Object.entries(handlers)) {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch (error) {
      console.debug(`Media action '${action}' is unavailable`, error);
    }
  }
}

async function playTrack(trackId) {
  const track = state.tracks.find((item) => item.id === Number(trackId));
  if (!track) return;
  state.queue = [...state.tracks];
  state.index = state.queue.findIndex((item) => item.id === track.id);
  setPlayback(track);
}

function addToQueue(trackId) {
  const track = state.tracks.find((item) => item.id === Number(trackId));
  if (!track) return;
  if (state.queue.some((queued) => queued.id === track.id)) return;
  state.queue.push(track);
}

function toggleFavorite(mediaType, mediaKey) {
  fetchJson('/api/favorites/toggle', {
    method: 'POST',
    body: JSON.stringify({ media_type: mediaType, media_key: mediaKey }),
  }).then(() => loadFavorites());
}

async function createPlaylist() {
  const name = window.prompt('Name your playlist');
  if (!name) return;
  await fetchJson('/api/playlists', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
  await loadPlaylists();
}

async function addCurrentTrackToPlaylist(playlistId) {
  if (!state.currentTrack) {
    alert('Pick a track first.');
    return;
  }
  await fetchJson(`/api/playlists/${playlistId}/tracks`, {
    method: 'POST',
    body: JSON.stringify({ track_id: state.currentTrack.id }),
  });
  await loadPlaylists();
}

document.querySelectorAll('.nav-item').forEach((button) => {
  button.addEventListener('click', () => renderView(button.dataset.view));
});

elements.setupForm.addEventListener('submit', handleSetup);
elements.loginForm.addEventListener('submit', handleLogin);
elements.logoutButton.addEventListener('click', handleLogout);
elements.scanLibraryButton.addEventListener('click', handleScanLibrary);
elements.newPlaylistButton.addEventListener('click', createPlaylist);

elements.themeToggle.addEventListener('click', () => {
  const dark = document.body.classList.contains('dark');
  setTheme(dark ? 'light' : 'dark');
});

elements.searchInput.addEventListener('input', (event) => {
  loadTracks(event.target.value.trim());
});

elements.globalSearchInput.addEventListener('input', (event) => {
  const query = event.target.value.trim();
  if (!query) {
    elements.searchContent.innerHTML = '<p>Search for a song, artist, or album.</p>';
    return;
  }
  fetchJson(`/api/search?q=${encodeURIComponent(query)}`)
    .then((response) => renderTracks(response.tracks || []));
});

document.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  const trackId = target.dataset.trackId;
  if (action === 'play') {
    await playTrack(trackId);
  }
  if (action === 'queue') {
    addToQueue(trackId);
  }
  if (action === 'favorite') {
    toggleFavorite(target.dataset.mediaType, target.dataset.mediaKey);
  }
  if (action === 'playlist-add') {
    await addCurrentTrackToPlaylist(target.dataset.playlistId);
  }
});

const storedTheme = localStorage.getItem('middlemusic-theme') || 'dark';
setTheme(storedTheme);
audio.volume = Number(elements.volumeSlider.value) / 100;
registerMediaActions();

audio.addEventListener('timeupdate', () => {
  if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
  const progress = (audio.currentTime / audio.duration) * 100;
  elements.seekSlider.value = progress;
  elements.timeCurrent.textContent = formatTime(audio.currentTime);
  elements.timeTotal.textContent = formatTime(audio.duration);
  if ('mediaSession' in navigator && navigator.mediaSession.setPositionState) {
    navigator.mediaSession.setPositionState({
      duration: audio.duration,
      playbackRate: audio.playbackRate,
      position: audio.currentTime,
    });
  }
});

audio.addEventListener('loadedmetadata', () => {
  elements.timeTotal.textContent = formatTime(audio.duration);
});

audio.addEventListener('ended', () => {
  if (state.repeat) {
    audio.currentTime = 0;
    audio.play();
    return;
  }
  if (state.index < state.queue.length - 1) {
    state.index += 1;
    setPlayback(state.queue[state.index]);
  }
});

audio.addEventListener('play', () => {
  elements.playButton.textContent = 'Pause';
  setMediaPlaybackState(true);
});

audio.addEventListener('pause', () => {
  elements.playButton.textContent = 'Play';
  setMediaPlaybackState(false);
});

elements.playButton.addEventListener('click', () => {
  if (!audio.src) return;
  if (audio.paused) {
    audio.play();
    elements.playButton.textContent = 'Pause';
  } else {
    audio.pause();
    elements.playButton.textContent = 'Play';
  }
});

elements.previousButton.addEventListener('click', () => {
  if (!state.currentTrack) return;
  const currentIndex = state.queue.findIndex((item) => item.id === state.currentTrack.id);
  if (currentIndex > 0) {
    setPlayback(state.queue[currentIndex - 1]);
  }
});

elements.nextButton.addEventListener('click', () => {
  if (!state.currentTrack) return;
  if (state.shuffle && state.queue.length > 1) {
    const choices = state.queue.filter((item) => item.id !== state.currentTrack.id);
    state.index = state.queue.findIndex((item) => item.id === choices[Math.floor(Math.random() * choices.length)].id);
    setPlayback(state.queue[state.index]);
    return;
  }
  if (state.index < state.queue.length - 1) {
    state.index += 1;
    setPlayback(state.queue[state.index]);
  }
});

elements.shuffleButton.addEventListener('click', () => {
  state.shuffle = !state.shuffle;
  elements.shuffleButton.style.background = state.shuffle ? 'var(--accent-soft)' : 'transparent';
});

elements.repeatButton.addEventListener('click', () => {
  state.repeat = !state.repeat;
  elements.repeatButton.style.background = state.repeat ? 'var(--accent-soft)' : 'transparent';
});

elements.volumeSlider.addEventListener('input', (event) => {
  audio.volume = Number(event.target.value) / 100;
});

elements.seekSlider.addEventListener('input', (event) => {
  if (!audio.duration) return;
  audio.currentTime = (Number(event.target.value) / 100) * audio.duration;
});

loadSession();
renderView('home');
