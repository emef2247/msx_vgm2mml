import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [input, output, modulePath] = process.argv.slice(2);
let mod;
try {
  mod = modulePath ? await import(pathToFileURL(modulePath).href) : await import('mgsc-js');
} catch (error) {
  console.error('MGSC setup error: ' + error.message);
  console.error('Run npm install --no-save --package-lock=false mgsc-js@2.0.0 in the repository, or supply --mgsc-module.');
  process.exit(2);
}
const {MGSC} = mod.default ?? mod;
await MGSC.initialize();
if (input === '--check') {
  console.log('MGSC initialized successfully');
  process.exit(0);
}
const result = MGSC.compile(fs.readFileSync(input, 'utf8'));
console.log(result.rawMessage);
if (!result.success) process.exit(1);
fs.writeFileSync(output, result.mgs);
