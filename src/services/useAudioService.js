// useAudioService.js
// Reactive hook that subscribes to the audioService singleton.
// Any component that calls this will re-render when audio state changes.
// Because the service polls at 500ms, position updates flow here automatically.

import { useState, useEffect } from 'react';
import { subscribe, getCurrentState } from './audioService';

export function useAudioService() {
  const [state, setState] = useState(getCurrentState);

  useEffect(() => {
    // Immediately sync in case state changed between render and effect
    setState(getCurrentState());
    const unsubscribe = subscribe(setState);
    return unsubscribe;
  }, []);

  return state;
}