import React, { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { colors } from '../theme/colors';
import { usePodcastStore } from '../store/podcastStore';
import { useAudioService } from '../services/useAudioService';
import * as AudioService from '../services/audioService';

export default function MiniPlayer({ onPress }) {
  const { currentEpisode, isPlaying, togglePlayback } = usePodcastStore();

  // Live position from the singleton — updates at 500ms intervals
  const audio = useAudioService();

  // Waveform pulse animation
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const pulseRef = useRef(null);

  useEffect(() => {
    if (isPlaying) {
      pulseRef.current = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.2, duration: 500, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 0.8, duration: 500, useNativeDriver: true }),
        ])
      );
      pulseRef.current.start();
    } else {
      pulseRef.current?.stop();
      Animated.timing(pulseAnim, { toValue: 1, duration: 200, useNativeDriver: true }).start();
    }
  }, [isPlaying]);

  if (!currentEpisode) return null;

  // Use live audio position when available, fall back to episode.progress
  const livePosition = audio.currentUri === currentEpisode.audioUrl
    ? audio.position
    : currentEpisode.progress;
  const duration = audio.duration || currentEpisode.duration || 1;
  const progressPct = Math.min(livePosition / duration, 1);

  function handleSkip() {
    const newPos = Math.min(livePosition + 30, duration);
    AudioService.seekTo(newPos);
  }

  return (
    <TouchableOpacity onPress={onPress} activeOpacity={0.9} style={styles.wrapper}>
      {/* Live progress bar at top */}
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${progressPct * 100}%` }]} />
      </View>

      <View style={styles.container}>
        {/* Thumbnail */}
        <LinearGradient
          colors={currentEpisode.thumbnailColor || ['#1a2a1a', '#2d4f2d']}
          style={styles.thumbnail}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
        />

        {/* Info */}
        <View style={styles.info}>
          <Text style={styles.title} numberOfLines={1}>{currentEpisode.title}</Text>
          <Text style={styles.source} numberOfLines={1}>{currentEpisode.source}</Text>
        </View>

        {/* Waveform */}
        <View style={styles.waveform}>
          {[8, 14, 10, 16, 6, 12, 9].map((h, i) => (
            <Animated.View
              key={i}
              style={[
                styles.bar,
                {
                  height: isPlaying ? h : 3,
                  transform: isPlaying ? [{ scaleY: pulseAnim }] : [{ scaleY: 1 }],
                  opacity: isPlaying ? 1 : 0.25,
                },
              ]}
            />
          ))}
        </View>

        {/* Play / Pause */}
        <TouchableOpacity style={styles.playBtn} onPress={togglePlayback}>
          {isPlaying ? (
            <View style={styles.pauseIcon}>
              <View style={styles.pauseBar} />
              <View style={styles.pauseBar} />
            </View>
          ) : (
            <View style={styles.playIcon} />
          )}
        </TouchableOpacity>

        {/* Skip +30 */}
        <TouchableOpacity style={styles.skipBtn} onPress={handleSkip}>
          <Text style={styles.skipArrow}>↻</Text>
          <Text style={styles.skipLabel}>30</Text>
        </TouchableOpacity>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: colors.surface,
    borderTopWidth: 0.5,
    borderTopColor: colors.border,
  },
  progressTrack: {
    height: 2,
    backgroundColor: colors.border,
  },
  progressFill: {
    height: 2,
    backgroundColor: colors.gold,
  },
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 12,
  },
  thumbnail: {
    width: 38,
    height: 38,
    borderRadius: 8,
  },
  info: { flex: 1 },
  title: { fontSize: 13, fontWeight: '600', color: colors.textPrimary },
  source: { fontSize: 11, color: colors.textMuted, marginTop: 1 },
  waveform: { flexDirection: 'row', alignItems: 'center', gap: 2, height: 20 },
  bar: { width: 2.5, backgroundColor: colors.gold, borderRadius: 1.5 },
  playBtn: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: colors.gold, justifyContent: 'center', alignItems: 'center',
  },
  playIcon: {
    width: 0, height: 0,
    borderTopWidth: 6, borderBottomWidth: 6, borderLeftWidth: 9,
    borderTopColor: 'transparent', borderBottomColor: 'transparent', borderLeftColor: colors.bg,
    marginLeft: 2,
  },
  pauseIcon: { flexDirection: 'row', gap: 3 },
  pauseBar: { width: 3, height: 11, backgroundColor: colors.bg, borderRadius: 1.5 },
  skipBtn: { width: 36, height: 36, justifyContent: 'center', alignItems: 'center' },
  skipArrow: { fontSize: 22, color: colors.textSecondary, lineHeight: 24, marginBottom: 4},
  skipLabel: { fontSize: 9, color: colors.textSecondary, fontWeight: '700', marginTop: -6 },
});