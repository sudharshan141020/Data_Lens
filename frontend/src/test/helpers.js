import { expect } from 'vitest';

// The bug class this guards against: writing a JS unicode escape (\u25B6,
// \u2192 ...) directly in JSX *text* or a double-quoted JSX attribute. Unlike
// a JS string, JSX does not interpret those, so the user sees the literal
// characters "\u25B6" instead of the symbol. It builds and lints clean, and
// it has shipped twice (DriftBanner, StoryMode). Any component rendered in a
// test should pass its container through this.
export function expectNoRawEscapes(container) {
  const text = container.textContent;
  expect(text, `rendered text contains a literal unicode escape: ${text.match(/\\u[0-9a-fA-F{]{1,6}/)?.[0]}`)
    .not.toMatch(/\\u[0-9a-fA-F{]/);
  container.querySelectorAll('[title],[aria-label],[placeholder],[alt]').forEach((el) => {
    ['title', 'aria-label', 'placeholder', 'alt'].forEach((attr) => {
      const v = el.getAttribute(attr);
      if (v) expect(v, `${attr} contains a literal unicode escape`).not.toMatch(/\\u[0-9a-fA-F{]/);
    });
  });
}
