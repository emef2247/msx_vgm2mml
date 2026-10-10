// SPDX-License-Identifier: MIT
// Copyright (c) 2026 emef2247
// libkss-js follows libkss ISC; embedded MSX drivers retain separate terms.
// See ../THIRD_PARTY_NOTICES.md for upstream notices and distribution scope.
// Export an already compiled MGS; no MGSC dependency or recompilation.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [input, output, duration, modulePath] = process.argv.slice(2);
try {
  const mod = modulePath ? await import(pathToFileURL(modulePath).href) : await import('libkss-js');
  const {KSS, KSSPlay} = mod.default ?? mod;
  await KSSPlay.initialize();
  if (input === '--check') {
    console.log('libkss initialized successfully');
    process.exit(0);
  }
  const milliseconds = Number(duration);
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) throw new Error('Invalid export duration');
  const kss = KSS.createUniqueInstance(new Uint8Array(fs.readFileSync(input)), 'regression.mgs');
  try {
    const data = await kss.toVGMAsync({duration: milliseconds, loop: 1});
    if (!data || !data.length) throw new Error('libkss produced no VGM');
    fs.writeFileSync(output, data);
  } finally {
    kss.release();
  }
} catch (error) {
  console.error('MGS export error: ' + error.message);
  process.exit(1);
}
