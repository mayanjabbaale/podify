import React, { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Svg, Circle } from 'react-native-svg';
import { colors } from '../theme/colors';
import { useDownloads } from '../services/useDownloads';

const RING_SIZE = 28;
const RING_STROKE = 2.5;
const RING_R = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R;

function formatProgress(seconds, total) {
  if (!seconds || seconds === 0) return null;
  if (seconds >= total * 0.95) return 'Played';
  const remaining = total - seconds;
  const mins = Math.floor(remaining / 60);
  if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}m left`;
  return `${mins}m left`;
}

// SVG progress ring for download state
function DownloadRing({ progress, isDownloaded, isDownloading, onPress }) {
  const strokeDash = RING_CIRCUMFERENCE * (1 - progress);

  return (
    <TouchableOpacity onPress={onPress} style={styles.downloadBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
      {isDownloaded ? (
        // Solid gold circle with checkmark
        <View style={styles.downloadedCircle}>
          <Text style={styles.downloadedCheck}>✓</Text>
        </View>
      ) : isDownloading ? (
        // Animated progress ring
        <Svg width={RING_SIZE} height={RING_SIZE}>
          {/* Track */}
          <Circle
            cx={RING_SIZE / 2}
            cy={RING_SIZE / 2}
            r={RING_R}
            stroke={colors.border}
            strokeWidth={RING_STROKE}
            fill="none"
          />
          {/* Progress fill */}
          <Circle
            cx={RING_SIZE / 2}
            cy={RING_SIZE / 2}
            r={RING_R}
            stroke={colors.gold}
            strokeWidth={RING_STROKE}
            fill="none"
            strokeDasharray={RING_CIRCUMFERENCE}
            strokeDashoffset={strokeDash}
            strokeLinecap="round"
            transform={`rotate(-90 ${RING_SIZE / 2} ${RING_SIZE / 2})`}
          />
        </Svg>
      ) : (
        // Download icon (arrow pointing down into tray)
        <View style={styles.downloadIcon}>
          <View style={styles.downloadArrowShaft} />
          <View style={styles.downloadArrowHead} />
          <View style={styles.downloadTray} />
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function EpisodeCard({ episode, onPress, onLongPress, isActive }) {
  const { startDownload, removeDownload, cancelDownload, isDownloading, isDownloaded, getProgress } =
    useDownloads();

  const progressStatus = formatProgress(episode.progress, episode.duration);
  const progressPercent = episode.duration > 0 ? episode.progress / episode.duration : 0;
  const downloading = isDownloading(episode.id);
  const downloaded = isDownloaded(episode.id) || !!episode.localAudioPath;
  const downloadProgress = getProgress(episode.id);

  // Determine if episode can be downloaded (has a real audioUrl)
  const canDownload = !!episode.audioUrl && !episode.audioUrl.includes('mock');

  function handleDownloadPress() {
    if (downloaded) {
      removeDownload(episode);
    } else if (downloading) {
      cancelDownload(episode.id);
    } else {
      startDownload(episode);
    }
  }

  return (
    <TouchableOpacity
      style={[styles.card, isActive && styles.cardActive]}
      onPress={() => onPress(episode)}
      onLongPress={() => onLongPress && onLongPress(episode)}
      activeOpacity={0.7}
    >
      {/* Thumbnail */}
      <LinearGradient
        colors={episode.thumbnailColor || ['#1a2a1a', '#2d4f2d']}
        style={styles.thumbnail}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
      >
        <View style={styles.thumbnailInner}>
          <View style={[styles.wave, { height: 6 }]} />
          <View style={[styles.wave, { height: 10, width: 20, marginTop: 3 }]} />
          <View style={[styles.wave, { height: 7, width: 16, marginTop: 3 }]} />
        </View>
        {/* Offline badge on thumbnail */}
        {downloaded && (
          <View style={styles.offlineBadge}>
            <Text style={styles.offlineBadgeText}>↓</Text>
          </View>
        )}
      </LinearGradient>

      {/* Info */}
      <View style={styles.info}>
        <Text style={styles.title} numberOfLines={2}>{episode.title}</Text>
        <Text style={styles.source} numberOfLines={1}>{episode.source}</Text>

        <View style={styles.meta}>
          <Text style={styles.duration}>{episode.durationLabel}</Text>
          {downloaded && (
            <>
              <View style={styles.dot} />
              <Text style={styles.offlineLabel}>Offline</Text>
            </>
          )}
          {!downloaded && progressStatus && (
            <>
              <View style={styles.dot} />
              <Text style={[styles.progressLabel, progressStatus === 'Played' && styles.progressPlayed]}>
                {progressStatus}
              </Text>
            </>
          )}
          {downloading && (
            <>
              <View style={styles.dot} />
              <Text style={styles.downloadingLabel}>
                {Math.round(downloadProgress * 100)}%
              </Text>
            </>
          )}
        </View>

        {/* Playback progress bar */}
        {progressPercent > 0 && progressPercent < 0.95 && (
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progressPercent * 100}%` }]} />
          </View>
        )}
      </View>

      {/* Right side controls */}
      <View style={styles.rightControls}>
        {/* Download button (only for episodes with real audio) */}
        {canDownload && (
          <DownloadRing
            progress={downloadProgress}
            isDownloaded={downloaded}
            isDownloading={downloading}
            onPress={handleDownloadPress}
          />
        )}

        {/* Play button */}
        <TouchableOpacity style={styles.playBtn} onPress={() => onPress(episode)}>
          {isActive ? (
            <View style={styles.pauseIcon}>
              <View style={styles.pauseBar} />
              <View style={styles.pauseBar} />
            </View>
          ) : (
            <View style={styles.playIcon} />
          )}
        </TouchableOpacity>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
    borderWidth: 0.5,
    borderColor: colors.border,
  },
  cardActive: {
    borderColor: colors.goldDim,
    borderWidth: 1,
  },
  thumbnail: {
    width: 52,
    height: 52,
    borderRadius: 10,
    marginRight: 12,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  thumbnailInner: {
    alignItems: 'flex-start',
  },
  wave: {
    height: 8,
    width: 24,
    backgroundColor: colors.gold,
    borderRadius: 2,
    opacity: 0.7,
  },
  offlineBadge: {
    position: 'absolute',
    bottom: 3,
    right: 3,
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.gold,
    justifyContent: 'center',
    alignItems: 'center',
  },
  offlineBadgeText: {
    fontSize: 8,
    color: colors.bg,
    fontWeight: '800',
  },
  info: {
    flex: 1,
    marginRight: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.textPrimary,
    lineHeight: 18,
    marginBottom: 2,
  },
  source: {
    fontSize: 11,
    color: colors.textMuted,
    marginBottom: 5,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  duration: {
    fontSize: 11,
    color: colors.textSecondary,
  },
  dot: {
    width: 3,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: colors.textMuted,
    marginHorizontal: 5,
  },
  progressLabel: {
    fontSize: 11,
    color: colors.gold,
  },
  progressPlayed: {
    color: colors.textMuted,
  },
  offlineLabel: {
    fontSize: 11,
    color: colors.gold,
  },
  downloadingLabel: {
    fontSize: 11,
    color: colors.gold,
  },
  progressTrack: {
    height: 2,
    backgroundColor: colors.border,
    borderRadius: 1,
    marginTop: 6,
    overflow: 'hidden',
  },
  progressFill: {
    height: 2,
    backgroundColor: colors.gold,
    borderRadius: 1,
  },
  rightControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },

  // Download ring
  downloadBtn: {
    width: RING_SIZE,
    height: RING_SIZE,
    justifyContent: 'center',
    alignItems: 'center',
  },
  downloadedCircle: {
    width: RING_SIZE,
    height: RING_SIZE,
    borderRadius: RING_SIZE / 2,
    backgroundColor: colors.goldMuted,
    borderWidth: 1.5,
    borderColor: colors.gold,
    justifyContent: 'center',
    alignItems: 'center',
  },
  downloadedCheck: {
    fontSize: 12,
    color: colors.gold,
    fontWeight: '700',
  },
  downloadIcon: {
    width: RING_SIZE,
    height: RING_SIZE,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: RING_SIZE / 2,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  downloadArrowShaft: {
    width: 2,
    height: 7,
    backgroundColor: colors.textSecondary,
    borderRadius: 1,
    marginBottom: 0,
  },
  downloadArrowHead: {
    width: 0,
    height: 0,
    borderLeftWidth: 4,
    borderRightWidth: 4,
    borderTopWidth: 5,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    borderTopColor: colors.textSecondary,
    marginBottom: 1,
  },
  downloadTray: {
    width: 10,
    height: 2,
    backgroundColor: colors.textSecondary,
    borderRadius: 1,
  },

  // Play button
  playBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.gold,
    justifyContent: 'center',
    alignItems: 'center',
  },
  playIcon: {
    width: 0,
    height: 0,
    borderTopWidth: 6,
    borderBottomWidth: 6,
    borderLeftWidth: 10,
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
    borderLeftColor: colors.bg,
    marginLeft: 2,
  },
  pauseIcon: {
    flexDirection: 'row',
    gap: 3,
  },
  pauseBar: {
    width: 3,
    height: 12,
    backgroundColor: colors.bg,
    borderRadius: 1.5,
  },
});