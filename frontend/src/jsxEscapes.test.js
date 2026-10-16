import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { findRawEscapes } from './test/jsxEscapeLint';

describe('findRawEscapes (the lint itself)', () => {
  it.each([
    ['escape in JSX text', '<button>\\u25B6 Present</button>'],
    ['escape after an expression in JSX text', '<span>{n} \\u2192 {m}</span>'],
    ['code-point form in JSX text', '<span aria-hidden="true">\\u{1F4CA}</span>'],
    ['escape in a double-quoted attribute', '<button title="Back \\u2192">x</button>'],
  ])('flags: %s', (_n, line) => {
    expect(findRawEscapes(line)).toHaveLength(1);
  });

  it.each([
    ['escape inside a JS expression string', "<button>{'\\u25B6'} Present</button>"],
    ['single-quoted JS string', "const label = 'Forecast \\u2192';"],
    ['double-quoted JS string in plain code', 'const arrow = "\\u2192";'],
    ['template literal', '<p>{`${a} \\u00d7 ${b}`}</p>'],
    ['line comment', '// shows \\u2192 in the tooltip'],
    ['block comment body', ' * the \\u25B6 glyph'],
    ['literal character (what we want)', '<span>▶ Present</span>'],
    ['escape inside a JSX expression attribute', '<Line label={{ value: "Go \\u2192" }} />'],
  ])('does not flag: %s', (_n, line) => {
    expect(findRawEscapes(line)).toEqual([]);
  });

  it('reports the line number', () => {
    expect(findRawEscapes('a\nb\n<i>\\u2713</i>')[0].line).toBe(3);
  });
});

function jsxFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return e.name === 'test' ? [] : jsxFiles(p);
    return e.name.endsWith('.jsx') && !e.name.endsWith('.test.jsx') ? [p] : [];
  });
}

describe('source scan', () => {
  const files = jsxFiles(path.join(process.cwd(), 'src'));

  it('finds the components to scan', () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(files.map((f) => [path.relative(process.cwd(), f), f]))('%s has no raw unicode escapes in JSX text or attributes', (_rel, file) => {
    const hits = findRawEscapes(fs.readFileSync(file, 'utf8'));
    expect(hits, hits.map((h) => `line ${h.line}: ${h.why}\n    ${h.text}`).join('\n')).toEqual([]);
  });
});
