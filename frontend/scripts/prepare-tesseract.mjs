import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const files = [
  ["node_modules/tesseract.js/dist/worker.min.js", "public/tesseract/worker.min.js"],
  ["node_modules/tesseract.js-core/tesseract-core-simd-lstm.wasm.js", "public/tesseract/tesseract-core-simd-lstm.wasm.js"],
  ["node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz", "public/tesseract/lang/eng.traineddata.gz"],
];

for (const [source, destination] of files) {
  const output = join(frontendRoot, destination);
  await mkdir(dirname(output), { recursive: true });
  await copyFile(join(frontendRoot, source), output);
}
