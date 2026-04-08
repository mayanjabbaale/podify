// useDownloads.js
// Reactive hook that subscribes to downloadService state.
// Returns current download states for all episodes, plus helper actions.

import { useState, useEffect } from 'react';
import {
  subscribeDownloads,
  downloadEpisode,
  cancelDownload,
  deleteDownload,
  getLocalPath,
} from './downloadService';
import { usePodcastStore } from '../store/podcastStore';

export function useDownloads() {
  const [downloads, setDownloads] = useState({});
  const { updateEpisodeLocalPath } = usePodcastStore();

  useEffect(() => {
    const unsub = subscribeDownloads(setDownloads);
    return unsub;
  }, []);

  function startDownload(episode) {
    if (!episode?.audioUrl || episode.audioUrl.includes('mock')) return;

    downloadEpisode({
      episodeId: episode.id,
      audioUrl: episode.audioUrl,
      onProgress: () => {}, // state flows through subscription
      onComplete: (localPath) => {
        updateEpisodeLocalPath(episode.id, localPath);
      },
      onError: (msg) => {
        console.warn('[Download] failed:', msg);
      },
    });
  }

  async function removeDownload(episode) {
    await deleteDownload(episode.id);
    updateEpisodeLocalPath(episode.id, null);
  }

  function getState(episodeId) {
    return downloads[episodeId] || null;
  }

  function isDownloading(episodeId) {
    return downloads[episodeId]?.status === 'downloading';
  }

  function isDownloaded(episodeId) {
    return downloads[episodeId]?.status === 'done';
  }

  function getProgress(episodeId) {
    return downloads[episodeId]?.progress ?? 0;
  }

  return {
    downloads,
    startDownload,
    removeDownload,
    cancelDownload,
    getState,
    isDownloading,
    isDownloaded,
    getProgress,
  };
}