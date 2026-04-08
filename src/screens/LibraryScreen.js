import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  StatusBar,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import EpisodeCard from '../components/EpisodeCard';
import MiniPlayer from '../components/MiniPlayer';
import { usePodcastStore } from '../store/podcastStore';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'unplayed', label: 'Unplayed' },
  { key: 'downloaded', label: 'Downloaded' },
];

export default function LibraryScreen({ navigation }) {
  const { filter, setFilter, currentEpisode, setCurrentEpisode, getFilteredEpisodes } =
    usePodcastStore();

  const episodes = getFilteredEpisodes();
  const unplayedCount = usePodcastStore(
    (s) => s.episodes.filter((e) => !e.played && e.progress === 0).length
  );

  function handleEpisodePress(episode) {
    setCurrentEpisode(episode);
    navigation.navigate('Player');
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg} />

      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.heading}>My Podcasts</Text>
            <Text style={styles.subheading}>
              {episodes.length} episode{episodes.length !== 1 ? 's' : ''} saved
            </Text>
          </View>

          <TouchableOpacity
            style={styles.addBtn}
            onPress={() => navigation.navigate('AddEpisode')}
            activeOpacity={0.8}
          >
            <Text style={styles.addBtnText}>+</Text>
          </TouchableOpacity>
        </View>

        {/* Filter tabs */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.filterRow}
          contentContainerStyle={styles.filterContent}
        >
          {FILTERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.filterTab, filter === f.key && styles.filterTabActive]}
              onPress={() => setFilter(f.key)}
              activeOpacity={0.7}
            >
              <Text
                style={[
                  styles.filterLabel,
                  filter === f.key && styles.filterLabelActive,
                ]}
              >
                {f.label}
              </Text>
              {f.key === 'unplayed' && unplayedCount > 0 && (
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>{unplayedCount}</Text>
                </View>
              )}
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Episode list */}
        <ScrollView
          style={styles.list}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
        >
          {episodes.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyEmoji}>🎙</Text>
              <Text style={styles.emptyTitle}>No episodes yet</Text>
              <Text style={styles.emptyBody}>
                Tap the + button to add your first YouTube speech
              </Text>
            </View>
          ) : (
            episodes.map((episode) => (
              <EpisodeCard
                key={episode.id}
                episode={episode}
                isActive={currentEpisode?.id === episode.id}
                onPress={handleEpisodePress}
              />
            ))
          )}

          {/* Bottom padding for mini player */}
          <View style={{ height: 20 }} />
        </ScrollView>
      </View>

      {/* Mini player */}
      {currentEpisode && (
        <MiniPlayer onPress={() => navigation.navigate('Player')} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 16,
  },
  heading: {
    fontSize: 26,
    fontWeight: '700',
    color: colors.textPrimary,
    letterSpacing: -0.5,
  },
  subheading: {
    fontSize: 13,
    color: colors.textMuted,
    marginTop: 2,
  },
  addBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.gold,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 4,
  },
  addBtnText: {
    fontSize: 24,
    color: colors.bg,
    fontWeight: '300',
    lineHeight: 28,
  },
  filterRow: {
    flexGrow: 0,
    marginBottom: 8,
  },
  filterContent: {
    paddingHorizontal: 20,
    gap: 8,
    flexDirection: 'row',
  },
  filterTab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
    backgroundColor: colors.surface,
    borderWidth: 0.5,
    borderColor: colors.border,
    gap: 5,
  },
  filterTabActive: {
    backgroundColor: colors.gold,
    borderColor: colors.gold,
  },
  filterLabel: {
    fontSize: 13,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  filterLabelActive: {
    color: colors.bg,
    fontWeight: '600',
  },
  badge: {
    backgroundColor: colors.bg,
    borderRadius: 8,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  badgeText: {
    fontSize: 10,
    color: colors.gold,
    fontWeight: '700',
  },
  list: {
    flex: 1,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: 80,
    paddingHorizontal: 40,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  emptyBody: {
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 20,
  },
});