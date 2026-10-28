// بررسی ایستا: سینتکس همه‌ی ماژول‌ها و حل شدن importهای نسبی (با پسوند .js).
// سرورلس هیچ پکیج npm ای نمی‌شناسد؛ فقط sdk و ماژول‌های خود پروژه.
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

const root = new URL('../tgcloud', import.meta.url).pathname;
const files = [];
(function walk(d) {
  for (const f of readdirSync(d)) {
    const p = join(d, f);
    statSync(p).isDirectory() ? walk(p) : p.endsWith('.js') && files.push(p);
  }
})(root);

let bad = 0;
for (const f of files) {
  const src = readFileSync(f, 'utf8');
  try {
    execFileSync(process.execPath, ['--check', '--input-type=module'], { input: src, stdio: ['pipe', 'pipe', 'pipe'] });
  } catch (e) {
    console.error(`SYNTAX ${f}\n${e.stderr}`);
    bad++;
  }
  for (const m of src.matchAll(/from\s+['"]([^'"]+)['"]/g)) {
    const spec = m[1];
    if (spec === 'sdk' || spec.startsWith('sdk/')) continue;
    if (!spec.startsWith('.') || !spec.endsWith('.js') || !existsSync(resolve(dirname(f), spec))) {
      console.error(`IMPORT ${f}: ${spec}`);
      bad++;
    }
  }
  if (/\.references\(|foreignKey\(/.test(src)) { console.error(`FK ${f}`); bad++; }
}
console.log(`${files.length} modules checked, ${bad} problems`);
process.exit(bad ? 1 : 0);
