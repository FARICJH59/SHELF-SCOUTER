/**
 * ResultsScreen – displays the fused multi-frame scan results.
 *
 * Shows:
 *  - Store / aisle / shelf context (from QGPS mapping)
 *  - Shelf summary from Gemma 4
 *  - Unique product count and frame count
 *  - Scrollable product list with confidence badges
 */

import React from "react";
import {
  FlatList,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import type { StackNavigationProp } from "@react-navigation/stack";
import type { Product, RootStackParamList } from "../types";

type ResultsRouteProp = RouteProp<RootStackParamList, "Results">;
type ResultsNavProp = StackNavigationProp<RootStackParamList, "Results">;

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "#22c55e",
  medium: "#eab308",
  low: "#f97316",
};

const CONFIDENCE_BG: Record<string, string> = {
  high: "#dcfce7",
  medium: "#fefce8",
  low: "#fff7ed",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const ConfidenceBadge: React.FC<{ level: string }> = ({ level }) => (
  <View
    style={[
      styles.badge,
      { backgroundColor: CONFIDENCE_BG[level] ?? "#f1f5f9" },
    ]}
  >
    <View
      style={[
        styles.badgeDot,
        { backgroundColor: CONFIDENCE_COLORS[level] ?? "#94a3b8" },
      ]}
    />
    <Text
      style={[
        styles.badgeText,
        { color: CONFIDENCE_COLORS[level] ?? "#64748b" },
      ]}
    >
      {level}
    </Text>
  </View>
);

const ProductCard: React.FC<{ product: Product; index: number }> = ({
  product,
  index,
}) => (
  <View style={styles.card}>
    <View style={styles.cardHeader}>
      <Text style={styles.cardIndex}>{index + 1}</Text>
      <View style={styles.cardTitleBlock}>
        <Text style={styles.cardName} numberOfLines={2}>
          {product.name}
        </Text>
        <Text style={styles.cardCategory}>{product.category}</Text>
      </View>
      <ConfidenceBadge level={product.confidence} />
    </View>

    <View style={styles.cardMeta}>
      {product.quantity != null && (
        <MetaItem label="Qty" value={String(product.quantity)} />
      )}
      {product.shelf_position && product.shelf_position !== "unknown" && (
        <MetaItem label="Position" value={product.shelf_position} />
      )}
      {product.label_text ? (
        <MetaItem label="Label" value={product.label_text} flex />
      ) : null}
    </View>
  </View>
);

const MetaItem: React.FC<{ label: string; value: string; flex?: boolean }> = ({
  label,
  value,
  flex,
}) => (
  <View style={[styles.metaItem, flex && { flex: 1 }]}>
    <Text style={styles.metaLabel}>{label}</Text>
    <Text style={styles.metaValue} numberOfLines={1}>
      {value}
    </Text>
  </View>
);

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export const ResultsScreen: React.FC = () => {
  const navigation = useNavigation<ResultsNavProp>();
  const route = useRoute<ResultsRouteProp>();
  const { result } = route.params;

  const handleScanAgain = () => {
    navigation.navigate("Camera");
  };

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Scan Results</Text>
        <TouchableOpacity
          style={styles.scanAgainButton}
          onPress={handleScanAgain}
        >
          <Text style={styles.scanAgainText}>Scan again</Text>
        </TouchableOpacity>
      </View>

      {/* Summary stats row */}
      <View style={styles.statsRow}>
        <StatCard
          value={String(result.total_unique_products)}
          label="Products"
        />
        {result.frames_processed != null && (
          <StatCard
            value={String(result.frames_processed)}
            label="Frames"
          />
        )}
        {result.aisle && result.aisle !== "unknown" && (
          <StatCard value={result.aisle} label="Aisle" small />
        )}
      </View>

      {/* Store / location context */}
      {(result.store_id || result.aisle || result.shelf) && (
        <View style={styles.locationCard}>
          {result.store_id && (
            <Text style={styles.locationText}>
              🏪 {result.store_id}
            </Text>
          )}
          {result.aisle && result.aisle !== "unknown" && (
            <Text style={styles.locationText}>📍 {result.aisle}</Text>
          )}
          {result.shelf && result.shelf !== "unknown" && (
            <Text style={styles.locationText}>📦 {result.shelf}</Text>
          )}
        </View>
      )}

      {/* Shelf summary */}
      {result.shelf_summary ? (
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Shelf summary</Text>
          <Text style={styles.summaryText}>{result.shelf_summary}</Text>
        </View>
      ) : null}

      {/* Product list */}
      <FlatList
        data={result.products}
        keyExtractor={(item, idx) => `${item.name}-${idx}`}
        renderItem={({ item, index }) => (
          <ProductCard product={item} index={index} />
        )}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <Text style={styles.emptyText}>No products detected.</Text>
        }
      />
    </SafeAreaView>
  );
};

const StatCard: React.FC<{ value: string; label: string; small?: boolean }> = ({
  value,
  label,
  small,
}) => (
  <View style={styles.statCard}>
    <Text
      style={[styles.statValue, small && styles.statValueSmall]}
      numberOfLines={1}
    >
      {value}
    </Text>
    <Text style={styles.statLabel}>{label}</Text>
  </View>
);

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: "#f8fafc",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingVertical: 14,
    backgroundColor: "#ffffff",
    borderBottomWidth: 1,
    borderBottomColor: "#e2e8f0",
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: "700",
    color: "#0f172a",
  },
  scanAgainButton: {
    backgroundColor: "#3b82f6",
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 10,
  },
  scanAgainText: {
    color: "#fff",
    fontWeight: "600",
    fontSize: 14,
  },
  statsRow: {
    flexDirection: "row",
    gap: 12,
    padding: 16,
  },
  statCard: {
    flex: 1,
    backgroundColor: "#ffffff",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  statValue: {
    fontSize: 24,
    fontWeight: "700",
    color: "#0f172a",
  },
  statValueSmall: {
    fontSize: 13,
  },
  statLabel: {
    fontSize: 12,
    color: "#64748b",
    marginTop: 2,
  },
  locationCard: {
    marginHorizontal: 16,
    marginBottom: 10,
    backgroundColor: "#ffffff",
    borderRadius: 12,
    padding: 14,
    gap: 4,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  locationText: {
    fontSize: 13,
    color: "#334155",
  },
  summaryCard: {
    marginHorizontal: 16,
    marginBottom: 12,
    backgroundColor: "#eff6ff",
    borderRadius: 12,
    padding: 14,
    borderLeftWidth: 3,
    borderLeftColor: "#3b82f6",
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: "600",
    color: "#3b82f6",
    textTransform: "uppercase",
    letterSpacing: 0.8,
    marginBottom: 4,
  },
  summaryText: {
    fontSize: 14,
    color: "#1e3a5f",
    lineHeight: 20,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 32,
    gap: 10,
  },
  card: {
    backgroundColor: "#ffffff",
    borderRadius: 14,
    padding: 14,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
  },
  cardIndex: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "#e2e8f0",
    textAlign: "center",
    lineHeight: 24,
    fontSize: 12,
    fontWeight: "700",
    color: "#64748b",
  },
  cardTitleBlock: {
    flex: 1,
  },
  cardName: {
    fontSize: 15,
    fontWeight: "600",
    color: "#0f172a",
  },
  cardCategory: {
    fontSize: 12,
    color: "#64748b",
    marginTop: 2,
    textTransform: "capitalize",
  },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    gap: 4,
  },
  badgeDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "capitalize",
  },
  cardMeta: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginTop: 10,
  },
  metaItem: {
    backgroundColor: "#f8fafc",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  metaLabel: {
    fontSize: 10,
    color: "#94a3b8",
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  metaValue: {
    fontSize: 13,
    color: "#334155",
    marginTop: 1,
  },
  emptyText: {
    textAlign: "center",
    color: "#94a3b8",
    fontSize: 15,
    marginTop: 40,
  },
});
