// Copies the built SPA (frontend/dist) over the directory FastAPI actually
// serves (app/static).
//
// `vite build` only writes frontend/dist, and the server never reads it. When
// the copy was a manual step, the committed app/static fell behind the source:
// the deployed UI was missing whole features while their code was in the repo.
// Running this from `npm run build:static` makes "build the frontend" and
// "ship the frontend" the same action, and CI fails if the two ever diverge.
import { cp, mkdir, readdir, rm, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, '..', 'dist');
const target = resolve(here, '..', '..', 'app', 'static');

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

if (!(await exists(join(dist, 'index.html')))) {
  console.error(`No build found at ${dist}. Run "npm run build" first.`);
  process.exit(1);
}

// assets/ is hash-named, so replacing the whole directory is what removes the
// previous build's bundle instead of accumulating one per release.
await rm(join(target, 'assets'), { recursive: true, force: true });
await mkdir(target, { recursive: true });

for (const entry of await readdir(dist)) {
  await cp(join(dist, entry), join(target, entry), { recursive: true });
}

console.log(`Copied ${dist} -> ${target}`);
