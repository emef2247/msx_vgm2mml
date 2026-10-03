// Explicit module paths keep the optional emulator dependencies outside Python.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [mml, output, duration, mgscPath, libkssPath] = process.argv.slice(2);
const mgscModule = await import(pathToFileURL(mgscPath).href);
const {MGSC} = mgscModule.default ?? mgscModule;
const {KSS, KSSPlay} = await import(pathToFileURL(libkssPath).href);
await MGSC.initialize();
await KSSPlay.initialize();
const bytes = fs.readFileSync(mml);
let source;
try {
  source = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
} catch {
  source = new TextDecoder('shift_jis').decode(bytes);
}
const result = MGSC.compile(source);
console.log(result.rawMessage);
if (!result.success) process.exit(2);
const kss = KSS.createUniqueInstance(result.mgs, 'roundtrip.mgs');
try {
  fs.writeFileSync(output, await kss.toVGMAsync({duration: Number(duration), loop: 1}));
} finally {
  kss.release();
}
