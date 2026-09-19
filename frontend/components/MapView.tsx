"use client";

import { useEffect, useRef } from "react";
import type { MapEntitiesOut } from "@/lib/types";
import "maplibre-gl/dist/maplibre-gl.css";

// The simulation's coordinates are plain km on a flat synthetic grid, not
// real lng/lat (see backend domain/geo.py) — MapLibre is used here purely
// as a rendering surface (blank style, no tile requests), treating x/y as
// an arbitrary local projection. This is an honest simplification: there is
// no real geography to show.
export function MapView({ entities }: { entities: MapEntitiesOut }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);

  useEffect(() => {
    let map: import("maplibre-gl").Map | null = null;
    let cancelled = false;

    (async () => {
      const { Map: MapLibreMap } = await import("maplibre-gl");
      if (cancelled || !containerRef.current) return;

      map = new MapLibreMap({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {},
          layers: [
            { id: "bg", type: "background", paint: { "background-color": "#0b0d10" } },
          ],
        },
        center: [0, 0],
        zoom: 10,
        attributionControl: false,
      });
      mapRef.current = map;

      map.on("load", () => {
        if (!map) return;

        const toFeatureCollection = (
          points: { location_x_km: number; location_y_km: number; id: string }[],
        ) => ({
          type: "FeatureCollection" as const,
          features: points.map((p) => ({
            type: "Feature" as const,
            properties: { id: p.id },
            geometry: {
              type: "Point" as const,
              coordinates: [p.location_x_km, p.location_y_km],
            },
          })),
        });

        const layers: [string, string, number][] = [
          ["merchants", "#e0a83c", 5],
          ["customers", "#5b9dff", 3],
          ["drivers", "#4cbb7d", 4],
        ];

        for (const [key, color, radius] of layers) {
          const points = entities[key as keyof MapEntitiesOut] as {
            location_x_km: number;
            location_y_km: number;
            id: string;
          }[];
          map.addSource(key, { type: "geojson", data: toFeatureCollection(points) });
          map.addLayer({
            id: key,
            type: "circle",
            source: key,
            paint: {
              "circle-radius": radius,
              "circle-color": color,
              "circle-opacity": 0.85,
            },
          });
        }

        const allPoints = [
          ...entities.merchants,
          ...entities.drivers,
          ...entities.customers,
        ];
        if (allPoints.length > 0) {
          const xs = allPoints.map((p) => p.location_x_km);
          const ys = allPoints.map((p) => p.location_y_km);
          map.fitBounds(
            [
              [Math.min(...xs), Math.min(...ys)],
              [Math.max(...xs), Math.max(...ys)],
            ],
            { padding: 30, animate: false },
          );
        }
      });
    })();

    return () => {
      cancelled = true;
      map?.remove();
    };
     
  }, [entities]);

  return (
    <div
      ref={containerRef}
      className="w-full h-[360px] rounded-md overflow-hidden border border-[var(--border)]"
    />
  );
}
