using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;

namespace FoveAI.Creative
{
    /// <summary>
    /// Ambient background music player for the VR room.
    /// Supports mood-based playlists, volume control, and Alice-driven music selection.
    /// Music can be streamed from backend or loaded from StreamingAssets.
    /// </summary>
    public class AmbientMusicPlayer : MonoBehaviour
    {
        [Header("Audio")]
        [SerializeField] private AudioSource musicSource;
        [Range(0f, 1f)] public float volume = 0.35f;
        public bool spatialAudio = false; // Background music = 2D by default

        [Header("Mood Playlists")]
        [Tooltip("URLs or file paths for each mood. Backend can push new tracks.")]
        public List<string> calmTracks = new List<string>();
        public List<string> happyTracks = new List<string>();
        public List<string> focusedTracks = new List<string>();
        public List<string> energeticTracks = new List<string>();
        public List<string> ambientTracks = new List<string>();

        [Header("Settings")]
        public bool shuffle = true;
        public bool loopPlaylist = true;
        public float crossfadeDuration = 2f;

        // State
        private string _currentMood = "ambient";
        private int _currentIndex = 0;
        private bool _isPlaying;
        private float _targetVolume;
        private List<string> _currentPlaylist = new List<string>();

        // Mood → playlist mapping
        private Dictionary<string, List<string>> _moodPlaylists;

        private void Awake()
        {
            if (musicSource == null)
            {
                musicSource = gameObject.AddComponent<AudioSource>();
            }
            musicSource.spatialBlend = spatialAudio ? 1f : 0f;
            musicSource.volume = 0f; // Start silent, fade in
            musicSource.loop = false;
            _targetVolume = volume;

            _moodPlaylists = new Dictionary<string, List<string>>
            {
                { "calm", calmTracks },
                { "happy", happyTracks },
                { "focused", focusedTracks },
                { "energetic", energeticTracks },
                { "ambient", ambientTracks },
            };

            // Default ambient tracks if none set
            if (ambientTracks.Count == 0)
            {
                ambientTracks.AddRange(new[]
                {
                    "https://cdn.pixabay.com/audio/2024/03/15/audio_1f4e8d2e3f.mp3",
                    "https://cdn.pixabay.com/audio/2024/02/11/audio_8b3e7c2a1d.mp3",
                });
                _moodPlaylists["ambient"] = ambientTracks;
            }
        }

        private void Update()
        {
            // Smooth volume control
            if (musicSource != null)
            {
                musicSource.volume = Mathf.Lerp(musicSource.volume, _isPlaying ? _targetVolume : 0f, Time.deltaTime / crossfadeDuration);
            }

            // Play next track when current ends
            if (_isPlaying && musicSource != null && !musicSource.isPlaying && musicSource.clip != null)
            {
                NextTrack();
            }
        }

        // ── Public API ──

        public void Play()
        {
            if (_currentPlaylist.Count == 0)
                SetMood(_currentMood);

            if (_currentPlaylist.Count > 0 && !_isPlaying)
            {
                _isPlaying = true;
                PlayTrack(_currentIndex);
            }
        }

        public void Pause()
        {
            _isPlaying = false;
            if (musicSource != null) musicSource.Pause();
        }

        public void Stop()
        {
            _isPlaying = false;
            if (musicSource != null)
            {
                musicSource.Stop();
                musicSource.clip = null;
            }
        }

        public void SetVolume(float vol)
        {
            volume = Mathf.Clamp01(vol);
            _targetVolume = volume;
        }

        public void SetMood(string mood)
        {
            _currentMood = mood.ToLowerInvariant();
            if (_moodPlaylists.TryGetValue(_currentMood, out var playlist))
            {
                _currentPlaylist = new List<string>(playlist);
            }
            else
            {
                _currentPlaylist = new List<string>(ambientTracks);
            }

            if (shuffle) ShufflePlaylist();

            _currentIndex = 0;
            if (_isPlaying) PlayTrack(0);
        }

        public void NextTrack()
        {
            if (_currentPlaylist.Count == 0) return;
            _currentIndex = (_currentIndex + 1) % _currentPlaylist.Count;
            if (_currentIndex == 0 && !loopPlaylist)
            {
                Stop();
                return;
            }
            PlayTrack(_currentIndex);
        }

        public void PreviousTrack()
        {
            if (_currentPlaylist.Count == 0) return;
            _currentIndex = (_currentIndex - 1 + _currentPlaylist.Count) % _currentPlaylist.Count;
            PlayTrack(_currentIndex);
        }

        public void AddTrack(string mood, string url)
        {
            if (!_moodPlaylists.ContainsKey(mood))
                _moodPlaylists[mood] = new List<string>();
            _moodPlaylists[mood].Add(url);
            if (mood == _currentMood)
                _currentPlaylist.Add(url);
        }

        public string GetCurrentMood() => _currentMood;
        public bool IsPlaying => _isPlaying;
        public string CurrentTrackName => _currentPlaylist.Count > 0 ? _currentPlaylist[_currentIndex] : "";

        // ── Internal ──

        private void PlayTrack(int index)
        {
            if (index < 0 || index >= _currentPlaylist.Count) return;
            string url = _currentPlaylist[index];
            StartCoroutine(LoadAndPlayTrack(url));
        }

        private IEnumerator LoadAndPlayTrack(string url)
        {
            // If it's a local file, load from StreamingAssets
            if (!url.StartsWith("http"))
            {
                string path = System.IO.Path.Combine(Application.streamingAssetsPath, url);
                using (UnityWebRequest req = UnityWebRequestMultimedia.GetAudioClip(path, AudioType.UNKNOWN))
                {
                    yield return req.SendWebRequest();
                    if (req.result == UnityWebRequest.Result.Success)
                    {
                        AudioClip clip = DownloadHandlerAudioClip.GetContent(req);
                        if (clip != null)
                        {
                            if (musicSource.clip != null) Destroy(musicSource.clip);
                            musicSource.clip = clip;
                            musicSource.Play();
                        }
                    }
                }
                yield break;
            }

            // Stream from URL — use backend proxy for cross-origin
            string proxyUrl = $"http://{FoveAI.Config.ConfigLoader.Settings.serverIp}:8402/api/audio/stream?url={UnityWebRequest.EscapeURL(url)}";

            using (UnityWebRequest req = UnityWebRequestMultimedia.GetAudioClip(proxyUrl, AudioType.UNKNOWN))
            {
                req.timeout = 30;
                yield return req.SendWebRequest();

                if (req.result == UnityWebRequest.Result.Success)
                {
                    AudioClip clip = DownloadHandlerAudioClip.GetContent(req);
                    if (clip != null)
                    {
                        if (musicSource.clip != null) Destroy(musicSource.clip);
                        musicSource.clip = clip;
                        musicSource.Play();
                        Debug.Log($"[AmbientMusic] Playing: {url}");
                    }
                }
                else
                {
                    Debug.LogWarning($"[AmbientMusic] Failed to load: {url} — {req.error}");
                    // Try next track
                    _currentIndex = (_currentIndex + 1) % _currentPlaylist.Count;
                    if (_currentIndex != 0)
                        PlayTrack(_currentIndex);
                }
            }
        }

        private void ShufflePlaylist()
        {
            for (int i = _currentPlaylist.Count - 1; i > 0; i--)
            {
                int j = Random.Range(0, i + 1);
                (_currentPlaylist[i], _currentPlaylist[j]) = (_currentPlaylist[j], _currentPlaylist[i]);
            }
        }
    }
}
