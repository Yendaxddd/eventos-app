// What the dashboards last heard from the server, by request. Shown at once when a page opens, then refreshed.
export const cache = new Map();
export const clearPanelCache = () => cache.clear();
