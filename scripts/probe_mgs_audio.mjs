// Measure real PCM output from an already compiled MGS. No compilation occurs.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [input, output, duration = '3000', modulePath] = process.argv.slice(2);
try {
  const mod = modulePath ? await import(pathToFileURL(modulePath).href) : await import('libkss-js');
  const {KSS, KSSPlay} = mod.default ?? mod;
  await KSSPlay.initialize();
  const ms = Number(duration);
  if (!Number.isFinite(ms) || ms <= 0) throw new Error('Invalid probe duration');
  const rate = 22050;
  const kss = KSS.createUniqueInstance(new Uint8Array(fs.readFileSync(input)), 'probe.mgs');
  const player = new KSSPlay(rate);
  try {
    player.setData(kss);
    player.reset();
    const samples = player.calc(Math.ceil(rate * ms / 1000));
    let peak = 0, energy = 0, nonzero = 0;
    for (const sample of samples) {
      peak = Math.max(peak, Math.abs(sample));
      energy += sample * sample;
      nonzero += Number(sample !== 0);
    }
    fs.writeFileSync(output, JSON.stringify({duration_ms: ms, sample_rate: rate,
      samples: samples.length, peak, rms: Math.sqrt(energy / samples.length),
      nonzero_samples: nonzero}, null, 2) + '\n');
  } finally {
    player.release();
    kss.release();
  }
} catch (error) {
  console.error('MGS audio probe error: ' + error.message);
  process.exit(1);
}
