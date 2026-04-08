import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Animated,
  Keyboard,
  ActivityIndicator,
  Alert,
  Clipboard,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { colors } from '../theme/colors';
import {usePodcastStore} from '../store/podcastStore';
import {
  fetchVideoMetadata,
  extractAudio,
  isValidYouTubeUrl,
} from '../services/extractionService';

const SCREEN_STATE = {
  IDLE: 'idle',
  TYPING: 'typing',
  INVALID: 'invalid',
  FETCHING_META: 'fetching_meta',
  PREVIEW: 'preview',
  EXTRACTING: 'extracting',
  SUCCESS: 'success',
  ERROR: 'error',
};

export default function AddEpisodeScreen({ navigation }) {
  const [url, setUrl] = useState('');
  const [screenState, setScreenState] = useState(SCREEN_STATE.IDLE);
  const [metadata, setMetadata] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [extractionProgress, setExtractionProgress] = useState(0);

  const addEpisode = usePodcastStore((s) => s.addEpisode);
  const episodes = usePodcastStore((s) => s.episodes);

  const previewAnim = useRef(new Animated.Value(0)).current;
  const shakeAnim = useRef(new Animated.Value(0)).current;
  const successAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (screenState === SCREEN_STATE.PREVIEW || screenState === SCREEN_STATE.EXTRACTING) {
      Animated.spring(previewAnim, {
        toValue: 1,
        useNativeDriver: true,
        tension: 80,
        friction: 10,
      }).start();
    } else if (screenState === SCREEN_STATE.SUCCESS) {
      Animated.timing(successAnim, { toValue: 1, duration: 300, useNativeDriver: true }).start();
    }
  }, [screenState]);

  useEffect(() => {
    if (screenState !== SCREEN_STATE.EXTRACTING) return;
    setExtractionProgress(0);
    const interval = setInterval(() => {
      setExtractionProgress((p) => {
        const next = p + Math.random() * 12;
        if (next >= 90) { clearInterval(interval); return 90; }
        return next;
      });
    }, 250);
    return () => clearInterval(interval);
  }, [screenState]);

  function handleUrlChange(text) {
    setUrl(text);
    if (screenState === SCREEN_STATE.INVALID) setScreenState(SCREEN_STATE.TYPING);
    if (screenState === SCREEN_STATE.PREVIEW || screenState === SCREEN_STATE.ERROR) {
      setScreenState(SCREEN_STATE.TYPING);
      setMetadata(null);
      Animated.timing(previewAnim, { toValue: 0, duration: 150, useNativeDriver: true }).start();
    }
  }

  async function handlePaste() {
    try {
      const text = await Clipboard.getString();
      if (text) handleUrlChange(text);
    } catch {}
  }

  function shake() {
    shakeAnim.setValue(0);
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 6, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0, duration: 60, useNativeDriver: true }),
    ]).start();
  }

  async function handleLookup() {
    Keyboard.dismiss();
    const trimmed = url.trim();
    if (!trimmed) return;

    if (!isValidYouTubeUrl(trimmed)) {
      setScreenState(SCREEN_STATE.INVALID);
      shake();
      return;
    }

    const alreadySaved = episodes.some((e) => e.youtubeUrl === trimmed);
    if (alreadySaved) {
      Alert.alert('Already saved', 'This video is already in your library.');
      return;
    }

    setScreenState(SCREEN_STATE.FETCHING_META);
    setErrorMsg('');

    try {
      const meta = await fetchVideoMetadata(trimmed);
      setMetadata(meta);
      setScreenState(SCREEN_STATE.PREVIEW);
    } catch {
      setErrorMsg('Could not load video info. Check the URL and try again.');
      setScreenState(SCREEN_STATE.ERROR);
    }
  }

  async function handleExtract() {
    setScreenState(SCREEN_STATE.EXTRACTING);
    try {
      const result = await extractAudio(url.trim());
      setExtractionProgress(100);
      await new Promise((r) => setTimeout(r, 400));

      addEpisode({
        id: Date.now().toString(),
        title: result.title,
        source: result.source,
        duration: result.duration,
        durationLabel: result.durationLabel,
        audioUrl: result.audioUrl,
        thumbnailColor: result.thumbnailColor,
        savedAt: new Date().toISOString(),
        played: false,
        progress: 0,
        youtubeUrl: url.trim(),
      });

      setScreenState(SCREEN_STATE.SUCCESS);
    } catch {
      setErrorMsg('Extraction failed. The video may be unavailable or too long.');
      setScreenState(SCREEN_STATE.ERROR);
    }
  }

  function handleReset() {
    setUrl('');
    setMetadata(null);
    setErrorMsg('');
    setScreenState(SCREEN_STATE.IDLE);
    previewAnim.setValue(0);
    successAnim.setValue(0);
  }

  const isLoading =
    screenState === SCREEN_STATE.FETCHING_META || screenState === SCREEN_STATE.EXTRACTING;
  const showLookup = [
    SCREEN_STATE.IDLE, SCREEN_STATE.TYPING,
    SCREEN_STATE.INVALID, SCREEN_STATE.ERROR,
  ].includes(screenState);

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.closeBtn}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.heading}>Add Episode</Text>
          <View style={{ width: 32 }} />
        </View>

        <Text style={styles.subheading}>
          Paste a YouTube link to save its audio as a podcast episode.
        </Text>

        {/* URL input */}
        <Animated.View style={{ transform: [{ translateX: shakeAnim }] }}>
          <View style={[
            styles.inputWrapper,
            screenState === SCREEN_STATE.INVALID && styles.inputError,
            (screenState === SCREEN_STATE.PREVIEW || screenState === SCREEN_STATE.SUCCESS) && styles.inputSuccess,
          ]}>
            <TextInput
              style={styles.input}
              value={url}
              onChangeText={handleUrlChange}
              placeholder="https://youtube.com/watch?v=..."
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              editable={!isLoading && screenState !== SCREEN_STATE.SUCCESS}
              onSubmitEditing={handleLookup}
              returnKeyType="search"
            />
            {url.length === 0 ? (
              <TouchableOpacity style={styles.pasteBtn} onPress={handlePaste}>
                <Text style={styles.pasteBtnText}>Paste</Text>
              </TouchableOpacity>
            ) : (!isLoading && screenState !== SCREEN_STATE.SUCCESS && (
              <TouchableOpacity style={styles.clearBtn} onPress={handleReset}>
                <Text style={styles.clearBtnText}>✕</Text>
              </TouchableOpacity>
            ))}
          </View>

          {screenState === SCREEN_STATE.INVALID && (
            <Text style={styles.errorText}>That doesn't look like a YouTube URL</Text>
          )}
          {screenState === SCREEN_STATE.ERROR && (
            <Text style={styles.errorText}>{errorMsg}</Text>
          )}
        </Animated.View>

        {/* Lookup button */}
        {showLookup && (
          <TouchableOpacity
            style={[styles.lookupBtn, !url.trim() && styles.disabled]}
            onPress={handleLookup}
            disabled={!url.trim()}
            activeOpacity={0.8}
          >
            <Text style={styles.lookupBtnText}>Look up video</Text>
          </TouchableOpacity>
        )}

        {/* Fetching metadata */}
        {screenState === SCREEN_STATE.FETCHING_META && (
          <View style={styles.statusRow}>
            <ActivityIndicator size="small" color={colors.gold} />
            <Text style={styles.statusText}>Fetching video info...</Text>
          </View>
        )}

        {/* Preview card */}
        {(screenState === SCREEN_STATE.PREVIEW || screenState === SCREEN_STATE.EXTRACTING) && metadata && (
          <Animated.View style={[styles.previewCard, {
            opacity: previewAnim,
            transform: [{ translateY: previewAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }],
          }]}>
            <LinearGradient
              colors={metadata.thumbnailColor}
              style={styles.previewBanner}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
            >
              <View style={styles.waveRow}>
                {[8, 14, 6, 18, 10, 14, 8, 12, 16, 8].map((h, i) => (
                  <View key={i} style={[styles.waveBar, { height: h }]} />
                ))}
              </View>
            </LinearGradient>

            <View style={styles.previewBody}>
              <Text style={styles.previewTitle} numberOfLines={2}>{metadata.title}</Text>
              <Text style={styles.previewSource}>{metadata.source}</Text>

              <View style={styles.tags}>
                {[`🎙 Audio only`, `⏱ ${metadata.durationLabel}`, `💾 ~${metadata.fileSizeMb} MB`].map((t) => (
                  <View key={t} style={styles.tag}>
                    <Text style={styles.tagText}>{t}</Text>
                  </View>
                ))}
              </View>

              {screenState === SCREEN_STATE.EXTRACTING && (
                <View style={styles.extractProgress}>
                  <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, { width: `${extractionProgress}%` }]} />
                  </View>
                  <Text style={styles.progressLabel}>
                    {extractionProgress < 30 ? 'Connecting to server...'
                      : extractionProgress < 60 ? 'Extracting audio track...'
                      : extractionProgress < 85 ? 'Converting to MP3...'
                      : 'Almost done...'}
                  </Text>
                </View>
              )}
            </View>
          </Animated.View>
        )}

        {/* Extract button */}
        {screenState === SCREEN_STATE.PREVIEW && (
          <TouchableOpacity style={styles.extractBtn} onPress={handleExtract} activeOpacity={0.85}>
            <LinearGradient
              colors={[colors.gold, colors.goldDim]}
              style={styles.extractBtnInner}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
            >
              <Text style={styles.extractBtnText}>Extract & Save</Text>
            </LinearGradient>
          </TouchableOpacity>
        )}

        {/* Extracting status */}
        {screenState === SCREEN_STATE.EXTRACTING && (
          <View style={styles.statusRow}>
            <ActivityIndicator size="small" color={colors.gold} />
            <Text style={styles.statusText}>Extracting audio...</Text>
          </View>
        )}

        {/* Success */}
        {screenState === SCREEN_STATE.SUCCESS && (
          <Animated.View style={[styles.successCard, { opacity: successAnim }]}>
            <View style={styles.successIcon}>
              <Text style={styles.successCheck}>✓</Text>
            </View>
            <Text style={styles.successTitle}>Saved to library!</Text>
            <Text style={styles.successBody}>"{metadata?.title}" is ready to listen.</Text>
            <View style={styles.successActions}>
              <TouchableOpacity style={styles.secondaryBtn} onPress={handleReset}>
                <Text style={styles.secondaryBtnText}>Add another</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.primaryBtn} onPress={() => navigation.goBack()}>
                <Text style={styles.primaryBtnText}>Go to library</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        )}

        {/* Recent */}
        {showLookup && episodes.length > 0 && (
          <View style={styles.recentSection}>
            <Text style={styles.recentLabel}>RECENTLY ADDED</Text>
            {episodes.slice(0, 3).map((ep) => (
              <View key={ep.id} style={styles.recentRow}>
                <LinearGradient
                  colors={ep.thumbnailColor}
                  style={styles.recentThumb}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 1 }}
                />
                <Text style={styles.recentTitle} numberOfLines={1}>{ep.title}</Text>
                <View style={styles.recentBadge}>
                  <Text style={styles.recentBadgeText}>✓</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  content: { padding: 20, paddingBottom: 60 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  closeBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: colors.surface,
    justifyContent: 'center', alignItems: 'center',
  },
  closeBtnText: { fontSize: 13, color: colors.textSecondary },
  heading: { fontSize: 18, fontWeight: '700', color: colors.textPrimary },
  subheading: {
    fontSize: 14, color: colors.textMuted, lineHeight: 20,
    marginBottom: 24, textAlign: 'center',
  },
  inputWrapper: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 14, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: 14, height: 52, marginBottom: 4,
  },
  inputError: { borderColor: colors.danger },
  inputSuccess: { borderColor: colors.goldDim },
  input: { flex: 1, fontSize: 14, color: colors.textPrimary, paddingRight: 8 },
  pasteBtn: {
    backgroundColor: colors.surfaceHigh,
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8,
  },
  pasteBtnText: { fontSize: 12, color: colors.gold, fontWeight: '600' },
  clearBtn: { padding: 4 },
  clearBtnText: { fontSize: 14, color: colors.textMuted },
  errorText: { fontSize: 12, color: colors.danger, marginBottom: 12, marginLeft: 4 },
  lookupBtn: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: 14, height: 50, justifyContent: 'center', alignItems: 'center', marginTop: 8,
  },
  disabled: { opacity: 0.4 },
  lookupBtnText: { fontSize: 15, fontWeight: '600', color: colors.textSecondary },
  statusRow: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'center', gap: 10, marginTop: 24,
  },
  statusText: { fontSize: 14, color: colors.textSecondary },
  previewCard: {
    backgroundColor: colors.surface, borderRadius: 16,
    overflow: 'hidden', borderWidth: 0.5, borderColor: colors.border,
    marginTop: 20, marginBottom: 4,
  },
  previewBanner: { height: 88, justifyContent: 'center', alignItems: 'center' },
  waveRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 4 },
  waveBar: { width: 3, backgroundColor: colors.gold, borderRadius: 2, opacity: 0.7 },
  previewBody: { padding: 14 },
  previewTitle: {
    fontSize: 15, fontWeight: '600', color: colors.textPrimary,
    marginBottom: 4, lineHeight: 20,
  },
  previewSource: { fontSize: 12, color: colors.textMuted, marginBottom: 12 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tag: {
    backgroundColor: colors.surfaceHigh,
    borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4,
  },
  tagText: { fontSize: 11, color: colors.textSecondary },
  extractProgress: { marginTop: 14 },
  progressTrack: {
    height: 3, backgroundColor: colors.border,
    borderRadius: 2, overflow: 'hidden', marginBottom: 6,
  },
  progressFill: { height: 3, backgroundColor: colors.gold, borderRadius: 2 },
  progressLabel: { fontSize: 12, color: colors.textSecondary },
  extractBtn: { borderRadius: 14, overflow: 'hidden', marginTop: 14, height: 52 },
  extractBtnInner: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  extractBtnText: { fontSize: 16, fontWeight: '700', color: colors.bg, letterSpacing: 0.3 },
  successCard: {
    backgroundColor: colors.surface, borderRadius: 16,
    padding: 24, alignItems: 'center', marginTop: 24,
    borderWidth: 0.5, borderColor: colors.goldMuted,
  },
  successIcon: {
    width: 52, height: 52, borderRadius: 26,
    backgroundColor: colors.goldMuted,
    justifyContent: 'center', alignItems: 'center', marginBottom: 14,
  },
  successCheck: { fontSize: 22, color: colors.gold, fontWeight: '700' },
  successTitle: { fontSize: 18, fontWeight: '700', color: colors.textPrimary, marginBottom: 6 },
  successBody: {
    fontSize: 13, color: colors.textMuted,
    textAlign: 'center', lineHeight: 18, marginBottom: 20,
  },
  successActions: { flexDirection: 'row', gap: 10 },
  secondaryBtn: {
    flex: 1, height: 44, borderRadius: 12,
    backgroundColor: colors.surfaceHigh, justifyContent: 'center', alignItems: 'center',
    borderWidth: 0.5, borderColor: colors.border,
  },
  secondaryBtnText: { fontSize: 14, color: colors.textSecondary, fontWeight: '600' },
  primaryBtn: {
    flex: 1, height: 44, borderRadius: 12,
    backgroundColor: colors.gold, justifyContent: 'center', alignItems: 'center',
  },
  primaryBtnText: { fontSize: 14, color: colors.bg, fontWeight: '700' },
  recentSection: { marginTop: 36 },
  recentLabel: {
    fontSize: 11, color: colors.textMuted, fontWeight: '600',
    letterSpacing: 0.8, marginBottom: 12,
  },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  recentThumb: { width: 34, height: 34, borderRadius: 8 },
  recentTitle: { flex: 1, fontSize: 13, color: colors.textSecondary },
  recentBadge: {
    width: 20, height: 20, borderRadius: 10,
    backgroundColor: colors.goldMuted, justifyContent: 'center', alignItems: 'center',
  },
  recentBadgeText: { fontSize: 10, color: colors.gold, fontWeight: '700' },
});