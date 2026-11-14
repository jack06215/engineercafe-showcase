import { go } from '@codemirror/lang-go';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { Compartment, EditorState, type Extension } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';
import { EditorView } from '@codemirror/view';
import { useColorScheme } from '@mui/material/styles';
import { basicSetup } from 'codemirror';
import { useEffect, useEffectEvent, useRef } from 'react';

// SPEC §6.2: the solution languages.
export type EditorLanguage = 'python' | 'go' | 'typescript';

const LANGUAGES: Record<EditorLanguage, () => Extension> = {
  python: () => python(),
  go: () => go(),
  typescript: () => javascript({ typescript: true }),
};

type Props = {
  value: string;
  onChange?: (value: string) => void;
  language: EditorLanguage;
  readOnly?: boolean;
  // The editor's accessible name ("Solution code").
  label: string;
  minHeight?: number;
};

// CodeMirror 6 with Python, Go or TypeScript highlighting, following the
// app's light/dark mode. Uncontrolled inside: edits go out through
// `onChange`, and a `value` that differs from the document (a reload)
// replaces it.
export const CodeEditor = ({
  value,
  onChange,
  language,
  readOnly = false,
  label,
  minHeight = 240,
}: Props) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const compartmentsRef = useRef({
    language: new Compartment(),
    theme: new Compartment(),
    readOnly: new Compartment(),
  });
  const { mode, systemMode } = useColorScheme();
  const dark = (mode === 'system' ? systemMode : mode) === 'dark';

  const emitChange = useEffectEvent((text: string) => {
    onChange?.(text);
  });

  const initial = useEffectEvent(() => ({ value, language, readOnly, dark }));

  // Create the view once; the effects below reconfigure it in place.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const start = initial();
    const c = compartmentsRef.current;
    const view = new EditorView({
      parent: container,
      state: EditorState.create({
        doc: start.value,
        extensions: [
          basicSetup,
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ 'aria-label': label }),
          EditorView.theme({
            '&': { minHeight: `${minHeight}px`, fontSize: '14px' },
            '.cm-scroller': { minHeight: `${minHeight}px` },
          }),
          c.language.of(LANGUAGES[start.language]()),
          c.theme.of(start.dark ? oneDark : []),
          c.readOnly.of(EditorState.readOnly.of(start.readOnly)),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) emitChange(update.state.doc.toString());
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [label, minHeight]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartmentsRef.current.language.reconfigure(
        LANGUAGES[language](),
      ),
    });
  }, [language]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartmentsRef.current.theme.reconfigure(dark ? oneDark : []),
    });
  }, [dark]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: compartmentsRef.current.readOnly.reconfigure(
        EditorState.readOnly.of(readOnly),
      ),
    });
  }, [readOnly]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current !== value) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    }
  }, [value]);

  return (
    <div
      ref={containerRef}
      css={(theme) => ({
        border: `1px solid ${(theme.vars ?? theme).palette.divider}`,
        borderRadius: theme.shape.borderRadius,
        overflow: 'hidden',
      })}
    />
  );
};
