/**
 * BoundingBoxOverlay – renders product bounding boxes over the camera preview.
 *
 * Uses react-native-svg to draw labelled rectangles around detected products.
 * Bounding box coordinates are normalised [0, 1] and scaled to the overlay
 * dimensions at render time.
 */

import React from "react";
import Svg, { Rect, Text as SvgText, G } from "react-native-svg";
import { StyleSheet, View } from "react-native";
import type { Product } from "../types";

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "#22c55e",   // green
  medium: "#eab308", // yellow
  low: "#f97316",    // orange
};

interface BoundingBoxOverlayProps {
  products: Product[];
  /** Pixel dimensions of the overlay view. */
  width: number;
  height: number;
}

export const BoundingBoxOverlay: React.FC<BoundingBoxOverlayProps> = ({
  products,
  width,
  height,
}) => {
  const productsWithBoxes = products.filter((p) => p.bbox != null);

  if (productsWithBoxes.length === 0) {
    return null;
  }

  return (
    <View style={[styles.overlay, { width, height }]} pointerEvents="none">
      <Svg width={width} height={height}>
        {productsWithBoxes.map((product, index) => {
          const box = product.bbox!;
          const x = box.x * width;
          const y = box.y * height;
          const w = box.width * width;
          const h = box.height * height;
          const color =
            CONFIDENCE_COLORS[product.confidence] ?? CONFIDENCE_COLORS.low;
          const label = product.name.length > 20
            ? product.name.slice(0, 18) + "…"
            : product.name;

          return (
            <G key={`${product.name}-${index}`}>
              {/* Bounding box rectangle */}
              <Rect
                x={x}
                y={y}
                width={w}
                height={h}
                stroke={color}
                strokeWidth={2}
                fill="transparent"
                rx={4}
              />
              {/* Label background */}
              <Rect
                x={x}
                y={y - 22}
                width={Math.min(label.length * 7.5 + 8, w)}
                height={20}
                fill={color}
                rx={4}
              />
              {/* Label text */}
              <SvgText
                x={x + 4}
                y={y - 6}
                fontSize={11}
                fontWeight="600"
                fill="#ffffff"
              >
                {label}
              </SvgText>
            </G>
          );
        })}
      </Svg>
    </View>
  );
};

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    top: 0,
    left: 0,
  },
});
