import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

/** Small location map (OpenStreetMap tiles). Uses a circle marker so no image assets are needed. */
export function MapView({ lat, lon, label }: { lat: number; lon: number; label: string }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const map = L.map(el.current, { zoomControl: false, attributionControl: true, scrollWheelZoom: false }).setView(
      [lat, lon],
      15,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    }).addTo(map);
    L.circleMarker([lat, lon], { radius: 9, color: "#0f6f99", weight: 3, fillColor: "#5cc8f2", fillOpacity: 0.9 })
      .addTo(map)
      .bindTooltip(label);
    return () => {
      map.remove();
    };
  }, [lat, lon, label]);
  return <div className="map" ref={el} role="img" aria-label={`Map: ${label}`} />;
}
