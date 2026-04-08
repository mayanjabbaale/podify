import { create } from 'zustand';

const MOCK_EPISODES = [
  {
    id: '1',
    title: 'The Future of AI with Sam Altman',
    source: 'Lex Fridman Podcast',
    duration: 4323, // seconds
    durationLabel: '1h 12m',
    audioUrl: null,
    thumbnailColor: ['#1a3a2a', '#2d6a4f'],
    savedAt: new Date('2024-01-15').toISOString(),
    played: false,
    progress: 1634, // seconds played
    youtubeUrl: 'https://youtube.com/watch?v=example1',
  },
  {
    id: '2',
    title: 'How to Build a Startup from Scratch',
    source: 'Y Combinator',
    duration: 2880,
    durationLabel: '48m',
    audioUrl: null,
    thumbnailColor: ['#2a1a3a', '#4f2d6a'],
    savedAt: new Date('2024-01-12').toISOString(),
    played: false,
    progress: 0,
    youtubeUrl: 'https://youtube.com/watch?v=example2',
  },
  {
    id: '3',
    title: 'Naval Ravikant on Wealth & Happiness',
    source: 'The Knowledge Project',
    duration: 7380,
    durationLabel: '2h 3m',
    audioUrl: null,
    thumbnailColor: ['#3a1a1a', '#6a2d2d'],
    savedAt: new Date('2024-01-10').toISOString(),
    played: true,
    progress: 7380,
    youtubeUrl: 'https://youtube.com/watch?v=example3',
  },
  {
    id: '4',
    title: 'The Psychology of Money',
    source: 'Talks at Google',
    duration: 3540,
    durationLabel: '59m',
    audioUrl: null,
    thumbnailColor: ['#1a2a3a', '#2d4f6a'],
    savedAt: new Date('2024-01-08').toISOString(),
    played: false,
    progress: 720,
    youtubeUrl: 'https://youtube.com/watch?v=example4',
  },
  {
    id: '5',
    title: 'Elon Musk on Mars, Tesla & the Future',
    source: 'TED',
    duration: 5400,
    durationLabel: '1h 30m',
    audioUrl: null,
    thumbnailColor: ['#1a3a3a', '#2d6a6a'],
    savedAt: new Date('2024-01-05').toISOString(),
    played: false,
    progress: 0,
    youtubeUrl: 'https://youtube.com/watch?v=example5',
  },
];

export const usePodcastStore = create((set, get) => ({
  episodes: MOCK_EPISODES,
  currentEpisode: MOCK_EPISODES[0],
  isPlaying: false,
  playbackSpeed: 1.0,
  sleepTimerMinutes: null,    // null = off, number = minutes remaining
  sleepTimerEndTime: null,    // Date.now() + ms when timer should fire
  filter: 'all',

  setFilter: (filter) => set({ filter }),

  setCurrentEpisode: (episode) => set({ currentEpisode: episode, isPlaying: true }),

  togglePlayback: () => set((state) => ({ isPlaying: !state.isPlaying })),

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  setSleepTimer: (minutes) => {
    if (!minutes) return set({ sleepTimerMinutes: null, sleepTimerEndTime: null });
    set({
      sleepTimerMinutes: minutes,
      sleepTimerEndTime: Date.now() + minutes * 60 * 1000,
    });
  },

  clearSleepTimer: () => set({ sleepTimerMinutes: null, sleepTimerEndTime: null }),

  playNext: () => {
    const { episodes, currentEpisode } = get();
    const idx = episodes.findIndex((e) => e.id === currentEpisode?.id);
    if (idx < episodes.length - 1) {
      set({ currentEpisode: episodes[idx + 1], isPlaying: true });
    }
  },

  playPrev: () => {
    const { episodes, currentEpisode } = get();
    const idx = episodes.findIndex((e) => e.id === currentEpisode?.id);
    if (idx > 0) {
      set({ currentEpisode: episodes[idx - 1], isPlaying: true });
    }
  },

  addEpisode: (episode) =>
    set((state) => ({ episodes: [episode, ...state.episodes] })),

  removeEpisode: (id) =>
    set((state) => ({ episodes: state.episodes.filter((e) => e.id !== id) })),

  updateProgress: (id, progress) =>
    set((state) => ({
      episodes: state.episodes.map((e) =>
        e.id === id ? { ...e, progress, played: progress >= e.duration * 0.95 } : e
      ),
    })),

  updateEpisodeLocalPath: (id, localAudioPath) =>
    set((state) => ({
      episodes: state.episodes.map((e) =>
        e.id === id ? { ...e, localAudioPath } : e
      ),
    })),

  getFilteredEpisodes: () => {
    const { episodes, filter } = get();
    if (filter === 'unplayed') return episodes.filter((e) => !e.played && e.progress === 0);
    if (filter === 'downloaded') return episodes.filter((e) => e.audioUrl !== null);
    return episodes;
  },
}));