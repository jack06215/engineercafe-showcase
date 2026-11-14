import { EditorView } from '@codemirror/view';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppProviders } from '@/common/providers';

import { CodeEditor } from './CodeEditor';

const viewOf = (label: string) => {
  const content = screen.getByLabelText(label);
  const view = EditorView.findFromDOM(content);
  if (!view) throw new Error('no editor view');
  return view;
};

describe('CodeEditor', () => {
  it('shows the value, reports edits and takes a new value from outside', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <AppProviders>
        <CodeEditor
          label="Solution code"
          language="python"
          value="def f():"
          onChange={onChange}
        />
      </AppProviders>,
    );
    const view = viewOf('Solution code');
    expect(view.state.doc.toString()).toBe('def f():');

    view.dispatch({ changes: { from: 8, insert: '\n    pass' } });
    expect(onChange).toHaveBeenLastCalledWith('def f():\n    pass');

    rerender(
      <AppProviders>
        <CodeEditor
          label="Solution code"
          language="go"
          value="func main() {}"
          onChange={onChange}
        />
      </AppProviders>,
    );
    expect(view.state.doc.toString()).toBe('func main() {}');
  });

  it('is read-only when asked', () => {
    render(
      <AppProviders>
        <CodeEditor
          label="Saved code"
          language="typescript"
          value="x"
          readOnly
        />
      </AppProviders>,
    );
    expect(viewOf('Saved code').state.readOnly).toBe(true);
  });
});
