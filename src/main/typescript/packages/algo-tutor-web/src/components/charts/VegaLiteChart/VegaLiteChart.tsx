import Alert from '@mui/material/Alert';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import embed, { type VisualizationSpec } from 'vega-embed';

import type { EventListenerHandler, View } from 'vega';

type Props = {
  // A Vega-Lite (or Vega) spec. The chart is re-embedded whenever this
  // object changes, so memoize it, and keep anything that changes often
  // (a selection, a threshold) in `signals` instead.
  spec: VisualizationSpec;
  // Values for the spec's params (Vega signals), applied to the live view
  // without re-embedding. Memoize this object too.
  signals?: Record<string, unknown>;
  // Called with the data row behind a clicked mark.
  onDatumClick?: (datum: Record<string, unknown>) => void;
};

// Renders a spec with vega-embed as SVG, without the export/source menu.
// `width: 'container'` in the spec fills the parent's width.
export const VegaLiteChart = ({ spec, signals, onDatumClick }: Props) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<View | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const handleClick = useEffectEvent((datum: unknown) => {
    if (datum && typeof datum === 'object') {
      onDatumClick?.(datum as Record<string, unknown>);
    }
  });

  const applySignals = useEffectEvent((view: View) => {
    if (!signals) return;
    for (const [name, value] of Object.entries(signals)) {
      view.signal(name, value);
    }
    void view.runAsync();
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let view: View | undefined;
    let finalize: (() => void) | undefined;
    const onClick: EventListenerHandler = (_event, item) => {
      handleClick(item?.datum);
    };
    embed(container, spec, { actions: false, renderer: 'svg' })
      .then((result) => {
        if (cancelled) {
          result.finalize();
          return;
        }
        view = result.view;
        finalize = result.finalize;
        viewRef.current = view;
        setError(null);
        applySignals(view);
        view.addEventListener('click', onClick);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason : new Error(String(reason)));
      });
    return () => {
      cancelled = true;
      viewRef.current = null;
      view?.removeEventListener('click', onClick);
      finalize?.();
    };
  }, [spec]);

  useEffect(() => {
    if (viewRef.current) applySignals(viewRef.current);
  }, [signals]);

  return (
    <>
      {error && <Alert severity="error">{error.message}</Alert>}
      <div ref={containerRef} css={{ width: '100%' }} />
    </>
  );
};
