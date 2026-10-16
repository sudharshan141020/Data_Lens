// Static companion to expectNoRawEscapes (helpers.js): finds JS unicode
// escapes (\u25B6, \u{1F4CA}) written where JSX will NOT interpret them --
// directly in JSX text, or in a double-quoted JSX attribute. Inside a real
// JS string ('...', `...`, or "..." in plain code) they are fine and common
// in this codebase, so those are deliberately not flagged.
//
// It is a line-based heuristic, not a parser. Known limits: a line with two
// apostrophes in JSX text can hide an escape between them (false negative),
// and an escape inside a nested template literal (`...${x ? `\u00d7` : ''}`)
// or on a multi-line template's continuation line would be flagged (false
// positive) -- in that case write the literal character instead. The render
// tests catch what this can't.
const ESC = /\\u(?:[0-9a-fA-F]{4}|\{[0-9a-fA-F]+\})/;

export function findRawEscapes(source) {
  const hits = [];
  source.split('\n').forEach((raw, i) => {
    const t = raw.trim();
    if (t.startsWith('//') || t.startsWith('*') || t.startsWith('/*')) return;

    // JSX attribute literal: name="..." with no space before '=' (JS assignments
    // are written `a = "..."`, and that IS a normal JS string).
    for (const m of raw.matchAll(/[\w-]="([^"\n]*)"/g)) {
      if (ESC.test(m[1])) hits.push({ line: i + 1, text: t, why: 'escape inside a double-quoted JSX attribute' });
    }

    const withoutStrings = raw
      .replace(/'(?:\\.|[^'\\])*'/g, "''")
      .replace(/`(?:\\.|[^`\\])*`/g, '``')
      .replace(/"(?:\\.|[^"\\])*"/g, '""');
    if (ESC.test(withoutStrings)) hits.push({ line: i + 1, text: t, why: 'escape outside any JS string (i.e. in JSX text)' });
  });
  return hits;
}
