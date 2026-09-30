import { useEffect, useState } from "react";

import type { LiveSnapshot } from "./types";

export type LiveState = { snapshot: LiveSnapshot | null; connected: boolean };

/** Subscribes to the site's Server-Sent Events stream (UI-002). EventSource reconnects itself. */
export function useLive(siteId: string): LiveState {
  const [state, setState] = useState<LiveState>({ snapshot: null, connected: false });
  useEffect(() => {
    const source = new EventSource(`/api/v1/live/stream?site_id=${encodeURIComponent(siteId)}`);
    const onData = (event: MessageEvent<string>) => {
      try {
        setState({ snapshot: JSON.parse(event.data) as LiveSnapshot, connected: true });
      } catch {
        /* ignore a malformed frame; the next one replaces it */
      }
    };
    source.addEventListener("snapshot", onData);
    source.addEventListener("sample", onData);
    source.onerror = () => setState((s) => ({ ...s, connected: false }));
    return () => source.close();
  }, [siteId]);
  return state;
}
