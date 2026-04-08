import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  PanResponder,
  Dimensions,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { colors } from '../theme/colors';
import { usePodcastStore } from '../store/podcastStore';
import { useAudioService } from '../services/useAudioService';
import * as AudioService from '../services/audioService';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const SEEK_BAR_WIDTH = SCREEN_WIDTH - 48;
const SPEED_OPTIONS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0];
const SLEEP_OPTIONS = [5, 10, 15, 20, 30, 45, 60];
const SKIP_SECONDS = 30;

function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatSleepRemaining(endTime) {
  if (!endTime) return null;
  const remaining = Math.max(0, Math.ceil((endTime - Date.now()) / 1000 / 60));
  return `${remaining}m`;
}

export default function PlayerScreen({ navigation }) {
  const {
    currentEpisode,
    isPlaying,
    playbackSpeed,
    sleepTimerEndTime,
    togglePlayback,
    setPlaybackSpeed,
    setSleepTimer,
    clearSleepTimer,
    updateProgress,
    playNext,
    playPrev,
    episodes,
  } = usePodcastStore();

  // Live audio state from the singleton service — safe to read in any component
  const audio = useAudioService();

  // ── Seek drag ─────────────────────────────────────────────────────────────
  const [seekPosition, setSeekPosition] = useState(null);
  const isSeeking = seekPosition !== null;
  const seekPositionRef = useRef(0);
  const positionRef = useRef(0);

  // ── UI ────────────────────────────────────────────────────────────────────
  const [showSpeedModal, setShowSpeedModal] = useState(false);
  const [showSleepModal, setShowSleepModal] = useState(false);
  const [sleepLabel, setSleepLabel] = useState(null);
  const artworkScale = useRef(new Animated.Value(1)).current;
  const artworkAnim = useRef(null);

  const currentIndex = episodes.findIndex((e) => e.id === currentEpisode?.id);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < episodes.length - 1;

  // Derived position — drag overrides live value
  const position = isSeeking ? seekPosition : audio.position;
  const duration = audio.duration || currentEpisode?.duration || 0;
  positionRef.current = position;

  // ── Load audio when episode changes ──────────────────────────────────────
  useEffect(() => {
    if (!currentEpisode) return;
    const isMock = !currentEpisode.audioUrl || currentEpisode.audioUrl.includes('mock');
    if (isMock) return;
    if (audio.currentUri === currentEpisode.audioUrl) {
      if (isPlaying) AudioService.play();
      return;
    }
    AudioService.loadAndPlay(currentEpisode.audioUrl, currentEpisode.progress || 0);
  }, [currentEpisode?.id]);

  // ── Sync play/pause ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!audio.isLoaded) return;
    isPlaying ? AudioService.play() : AudioService.pause();
  }, [isPlaying, audio.isLoaded]);

  // ── Sync speed ────────────────────────────────────────────────────────────
  useEffect(() => {
    AudioService.setRate(playbackSpeed);
  }, [playbackSpeed]);

  // ── Persist progress every 5 s ───────────────────────────────────────────
  useEffect(() => {
    if (!audio.isLoaded || !currentEpisode) return;
    const id = setInterval(() => updateProgress(currentEpisode.id, audio.position), 5000);
    return () => clearInterval(id);
  }, [audio.isLoaded, currentEpisode?.id]);

  // ── Auto-advance on finish ────────────────────────────────────────────────
  const prevPos = useRef(0);
  useEffect(() => {
    if (duration > 0 && audio.position >= duration - 1 && prevPos.current < duration - 1) {
      updateProgress(currentEpisode?.id, duration);
      playNext();
    }
    prevPos.current = audio.position;
  }, [audio.position]);

  // ── Artwork pulse ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (isPlaying) {
      artworkAnim.current = Animated.loop(
        Animated.sequence([
          Animated.timing(artworkScale, { toValue: 1.03, duration: 2000, useNativeDriver: true }),
          Animated.timing(artworkScale, { toValue: 1.0, duration: 2000, useNativeDriver: true }),
        ])
      );
      artworkAnim.current.start();
    } else {
      artworkAnim.current?.stop();
      Animated.timing(artworkScale, { toValue: 1.0, duration: 300, useNativeDriver: true }).start();
    }
  }, [isPlaying]);

  // ── Sleep timer ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!sleepTimerEndTime) { setSleepLabel(null); return; }
    const id = setInterval(() => {
      const remaining = sleepTimerEndTime - Date.now();
      if (remaining <= 0) {
        clearSleepTimer();
        AudioService.pause();
        if (isPlaying) togglePlayback();
        clearInterval(id);
      } else {
        setSleepLabel(formatSleepRemaining(sleepTimerEndTime));
      }
    }, 5000);
    setSleepLabel(formatSleepRemaining(sleepTimerEndTime));
    return () => clearInterval(id);
  }, [sleepTimerEndTime]);

  // ── Save progress on screen close ────────────────────────────────────────
  useEffect(() => {
    return () => updateProgress(currentEpisode?.id, positionRef.current);
  }, []);

  // ── Seek pan responder ────────────────────────────────────────────────────
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => {
        const x = Math.max(0, Math.min(e.nativeEvent.locationX, SEEK_BAR_WIDTH));
        seekPositionRef.current = x;
        setSeekPosition((x / SEEK_BAR_WIDTH) * (positionRef.current > 0 ? duration : 1));
      },
      onPanResponderMove: (e) => {
        const x = Math.max(0, Math.min(e.nativeEvent.locationX, SEEK_BAR_WIDTH));
        seekPositionRef.current = x;
        setSeekPosition((x / SEEK_BAR_WIDTH) * (duration || 1));
      },
      onPanResponderRelease: () => {
        const newPos = (seekPositionRef.current / SEEK_BAR_WIDTH) * (duration || 1);
        positionRef.current = newPos;
        setSeekPosition(null);
        AudioService.seekTo(newPos);
        updateProgress(currentEpisode?.id, newPos);
      },
    })
  ).current;

  function skip(seconds) {
    const newPos = Math.max(0, Math.min(positionRef.current + seconds, duration));
    positionRef.current = newPos;
    AudioService.seekTo(newPos);
    updateProgress(currentEpisode?.id, newPos);
  }

  const progressPct = duration > 0 ? Math.min(position / duration, 1) : 0;
  const thumbX = progressPct * SEEK_BAR_WIDTH;
  const remaining = Math.max(0, duration - position);

  if (!currentEpisode) {
    return (
      <SafeAreaView style={styles.safe}>
        <TouchableOpacity style={styles.closeBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.closeBtnText}>↓</Text>
        </TouchableOpacity>
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No episode selected</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.closeBtn} onPress={() => navigation.goBack()}>
          <Text style={styles.closeBtnText}>↓</Text>
        </TouchableOpacity>
        <Text style={styles.headerLabel}>NOW PLAYING</Text>
        <TouchableOpacity style={styles.moreBtn}>
          <View style={styles.moreDot} />
          <View style={styles.moreDot} />
          <View style={styles.moreDot} />
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        {/* Artwork */}
        <Animated.View style={[styles.artworkWrapper, { transform: [{ scale: artworkScale }] }]}>
          <LinearGradient
            colors={currentEpisode.thumbnailColor || ['#1a3a2a', '#2d6a4f']}
            style={styles.artwork}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
          >
            {[72, 52, 36, 22].map((r, i) => (
              <View key={i} style={[styles.ring, {
                width: r * 2, height: r * 2, borderRadius: r, opacity: 0.08 + i * 0.06,
              }]} />
            ))}
            <View style={styles.centerDot} />
            {isPlaying && (
              <View style={styles.artworkWave}>
                {[6, 12, 8, 16, 10, 18, 8, 14, 10, 6].map((h, i) => (
                  <View key={i} style={[styles.artworkWaveBar, { height: h }]} />
                ))}
              </View>
            )}
          </LinearGradient>
        </Animated.View>

        {/* Info */}
        <View style={styles.info}>
          <Text style={styles.title} numberOfLines={2}>{currentEpisode.title}</Text>
          <Text style={styles.source}>{currentEpisode.source}</Text>
        </View>

        {/* Seek bar */}
        <View style={styles.seekSection}>
          <View style={styles.seekBar} {...panResponder.panHandlers} hitSlop={{ top: 16, bottom: 16 }}>
            <View style={styles.seekTrack}>
              <View style={[styles.seekFill, { width: `${progressPct * 100}%` }]} />
            </View>
            <View style={[styles.seekThumb, { left: thumbX - 8 }]} />
          </View>
          <View style={styles.seekTimes}>
            <Text style={styles.seekTime}>{formatTime(position)}</Text>
            <Text style={styles.seekTime}>−{formatTime(remaining)}</Text>
          </View>
        </View>

        {/* Playback controls */}
        <View style={styles.controls}>
          <TouchableOpacity
            style={[styles.skipEpBtn, !hasPrev && styles.disabled]}
            onPress={playPrev} disabled={!hasPrev}
          >
            <View style={styles.skipEpIcon}>
              <View style={[styles.skipTriangle, styles.skipLeft]} />
              <View style={styles.skipBar} />
            </View>
          </TouchableOpacity>

          <TouchableOpacity style={styles.skipBtn} onPress={() => skip(-SKIP_SECONDS)}>
            <Text style={styles.skipBtnNumber}>30</Text>
            <View style={styles.skipBtnArc}><Text style={styles.skipBtnArrow}>↺</Text></View>
          </TouchableOpacity>

          <TouchableOpacity style={styles.playBtn} onPress={togglePlayback} activeOpacity={0.85}>
            {audio.isBuffering ? (
              <View style={styles.bufferingDots}>
                {[0, 1, 2].map((i) => <View key={i} style={styles.bufferingDot} />)}
              </View>
            ) : isPlaying ? (
              <View style={styles.pauseIcon}>
                <View style={styles.pauseBar} />
                <View style={styles.pauseBar} />
              </View>
            ) : (
              <View style={styles.playIcon} />
            )}
          </TouchableOpacity>

          <TouchableOpacity style={styles.skipBtn} onPress={() => skip(SKIP_SECONDS)}>
            <Text style={styles.skipBtnNumber}>30</Text>
            <View style={styles.skipBtnArc}><Text style={styles.skipBtnArrow}>↻</Text></View>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.skipEpBtn, !hasNext && styles.disabled]}
            onPress={playNext} disabled={!hasNext}
          >
            <View style={styles.skipEpIcon}>
              <View style={styles.skipBar} />
              <View style={[styles.skipTriangle, styles.skipRight]} />
            </View>
          </TouchableOpacity>
        </View>

        {/* Speed & Sleep */}
        <View style={styles.bottomRow}>
          <TouchableOpacity style={styles.bottomPill} onPress={() => setShowSpeedModal(true)}>
            <Text style={styles.bottomPillText}>{playbackSpeed}×</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.bottomPill, sleepLabel && styles.bottomPillActive]}
            onPress={() => setShowSleepModal(true)}
          >
            <Text style={[styles.bottomPillText, sleepLabel && styles.bottomPillTextActive]}>
              {sleepLabel ? `Sleep ${sleepLabel}` : '☽ Sleep'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Speed modal */}
      <Modal visible={showSpeedModal} transparent animationType="slide" onRequestClose={() => setShowSpeedModal(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowSpeedModal(false)}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Playback Speed</Text>
            <View style={styles.speedGrid}>
              {SPEED_OPTIONS.map((speed) => (
                <TouchableOpacity
                  key={speed}
                  style={[styles.speedOption, playbackSpeed === speed && styles.speedOptionActive]}
                  onPress={() => { setPlaybackSpeed(speed); setShowSpeedModal(false); }}
                >
                  <Text style={[styles.speedOptionText, playbackSpeed === speed && styles.speedOptionTextActive]}>
                    {speed}×
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Sleep modal */}
      <Modal visible={showSleepModal} transparent animationType="slide" onRequestClose={() => setShowSleepModal(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowSleepModal(false)}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Sleep Timer</Text>
            {sleepTimerEndTime && (
              <TouchableOpacity style={styles.sleepCancelBtn} onPress={() => { clearSleepTimer(); setShowSleepModal(false); }}>
                <Text style={styles.sleepCancelText}>Cancel timer ({sleepLabel})</Text>
              </TouchableOpacity>
            )}
            <View style={styles.sleepGrid}>
              {SLEEP_OPTIONS.map((mins) => (
                <TouchableOpacity
                  key={mins}
                  style={styles.sleepOption}
                  onPress={() => { setSleepTimer(mins); setShowSleepModal(false); }}
                >
                  <Text style={styles.sleepOptionText}>{mins}</Text>
                  <Text style={styles.sleepOptionUnit}>min</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </TouchableOpacity>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12,
  },
  closeBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center' },
  closeBtnText: { fontSize: 18, color: colors.textSecondary, lineHeight: 22 },
  headerLabel: { fontSize: 11, fontWeight: '600', color: colors.textMuted, letterSpacing: 1.2 },
  moreBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surface, justifyContent: 'center', alignItems: 'center', gap: 3 },
  moreDot: { width: 3, height: 3, borderRadius: 1.5, backgroundColor: colors.textSecondary },
  content: { flex: 1, paddingHorizontal: 24, paddingBottom: 32, justifyContent: 'space-between' },
  artworkWrapper: { alignSelf: 'center', marginTop: 8 },
  artwork: { width: SCREEN_WIDTH - 80, height: SCREEN_WIDTH - 80, borderRadius: 24, justifyContent: 'center', alignItems: 'center', overflow: 'hidden' },
  ring: { position: 'absolute', borderWidth: 1, borderColor: colors.gold },
  centerDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: colors.gold, opacity: 0.9 },
  artworkWave: { position: 'absolute', bottom: 20, flexDirection: 'row', alignItems: 'flex-end', gap: 3 },
  artworkWaveBar: { width: 3, backgroundColor: colors.gold, borderRadius: 2, opacity: 0.6 },
  info: { marginTop: 24 },
  title: { fontSize: 20, fontWeight: '700', color: colors.textPrimary, letterSpacing: -0.3, marginBottom: 6, lineHeight: 26 },
  source: { fontSize: 14, color: colors.textMuted },
  seekSection: {},
  seekBar: { height: 20, justifyContent: 'center', marginBottom: 8 },
  seekTrack: { height: 3, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
  seekFill: { height: 3, backgroundColor: colors.gold, borderRadius: 2 },
  seekThumb: {
    position: 'absolute', width: 16, height: 16, borderRadius: 8, backgroundColor: colors.gold, top: 2,
    shadowColor: colors.gold, shadowOpacity: 0.4, shadowRadius: 4, shadowOffset: { width: 0, height: 0 }, elevation: 4,
  },
  seekTimes: { flexDirection: 'row', justifyContent: 'space-between' },
  seekTime: { fontSize: 12, color: colors.textMuted },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 4 },
  skipEpBtn: { width: 36, height: 36, justifyContent: 'center', alignItems: 'center' },
  skipEpIcon: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  skipTriangle: { width: 0, height: 0, borderTopWidth: 8, borderBottomWidth: 8 },
  skipLeft: { borderRightWidth: 12, borderTopColor: 'transparent', borderBottomColor: 'transparent', borderRightColor: colors.textSecondary },
  skipRight: { borderLeftWidth: 12, borderTopColor: 'transparent', borderBottomColor: 'transparent', borderLeftColor: colors.textSecondary },
  skipBar: { width: 3, height: 16, backgroundColor: colors.textSecondary, borderRadius: 1.5 },
  skipBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  skipBtnNumber: { fontSize: 11, fontWeight: '700', color: colors.textSecondary, position: 'absolute' },
  skipBtnArc: { position: 'absolute' },
  skipBtnArrow: { fontSize: 36, color: colors.textSecondary, lineHeight: 40 },
  playBtn: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: colors.gold, justifyContent: 'center', alignItems: 'center',
    shadowColor: colors.gold, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
  playIcon: { width: 0, height: 0, borderTopWidth: 12, borderBottomWidth: 12, borderLeftWidth: 20, borderTopColor: 'transparent', borderBottomColor: 'transparent', borderLeftColor: colors.bg, marginLeft: 4 },
  pauseIcon: { flexDirection: 'row', gap: 6 },
  pauseBar: { width: 4, height: 22, backgroundColor: colors.bg, borderRadius: 2 },
  bufferingDots: { flexDirection: 'row', gap: 5 },
  bufferingDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.bg, opacity: 0.7 },
  disabled: { opacity: 0.25 },
  bottomRow: { flexDirection: 'row', justifyContent: 'center', gap: 12 },
  bottomPill: { backgroundColor: colors.surface, borderRadius: 20, paddingHorizontal: 18, paddingVertical: 10, borderWidth: 0.5, borderColor: colors.border },
  bottomPillActive: { borderColor: colors.goldDim, backgroundColor: colors.goldMuted },
  bottomPillText: { fontSize: 14, fontWeight: '600', color: colors.textSecondary },
  bottomPillTextActive: { color: colors.gold },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: colors.surface, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40, borderTopWidth: 0.5, borderColor: colors.border },
  modalHandle: { width: 36, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 16, fontWeight: '700', color: colors.textPrimary, marginBottom: 20, textAlign: 'center' },
  speedGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center' },
  speedOption: { width: 80, height: 52, borderRadius: 12, backgroundColor: colors.surfaceHigh, justifyContent: 'center', alignItems: 'center', borderWidth: 0.5, borderColor: colors.border },
  speedOptionActive: { backgroundColor: colors.goldMuted, borderColor: colors.goldDim },
  speedOptionText: { fontSize: 16, fontWeight: '600', color: colors.textSecondary },
  speedOptionTextActive: { color: colors.gold },
  sleepCancelBtn: { backgroundColor: colors.surfaceHigh, borderRadius: 12, padding: 12, alignItems: 'center', marginBottom: 16, borderWidth: 0.5, borderColor: colors.goldDim },
  sleepCancelText: { fontSize: 14, color: colors.gold, fontWeight: '600' },
  sleepGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'center' },
  sleepOption: { width: 72, height: 64, borderRadius: 12, backgroundColor: colors.surfaceHigh, justifyContent: 'center', alignItems: 'center', borderWidth: 0.5, borderColor: colors.border },
  sleepOptionText: { fontSize: 20, fontWeight: '700', color: colors.textPrimary },
  sleepOptionUnit: { fontSize: 10, color: colors.textMuted, marginTop: 2 },
  emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyText: { fontSize: 16, color: colors.textMuted },
});