import { readdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)), 'frontend', 'src');

async function filesUnder(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await filesUnder(path));
    else if (/\.(ts|tsx)$/.test(entry.name)) files.push(path);
  }
  return files;
}

const violations = [];
for (const path of await filesUnder(root)) {
  const source = await readFile(path, 'utf8');
  const relative = path.slice(root.length + 1).replaceAll('\\', '/');
  if (relative.startsWith('components/') && source.includes("services/client")) {
    violations.push(`${relative}: component imports transport client`);
  }
  if (relative.startsWith('services/') && source.includes("../components/")) {
    violations.push(`${relative}: service imports component`);
  }
}

if (violations.length) {
  console.error(violations.join('\n'));
  process.exitCode = 1;
} else {
  console.log('frontend architecture boundaries: OK');
}
