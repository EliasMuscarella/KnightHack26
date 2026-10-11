/**
 * Test-only module resolution for the briefing model: `@/x` -> `src/x.ts` and extensionless
 * relative imports -> `.ts`, so `node --experimental-strip-types --test` can load
 * lib/briefing/build.ts (which imports `@/lib/names` and `./types` like the rest of the app).
 * Import this first, then load the module under test with a dynamic `import()`.
 */
import { existsSync, statSync } from "node:fs";
import { registerHooks } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const SRC = fileURLToPath(new URL("../../", import.meta.url));

function withTs(path: string): string | null {
  for (const p of [path, `${path}.ts`, `${path}.tsx`, `${path}/index.ts`]) if (existsSync(p) && statSync(p).isFile()) return p;
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const file = withTs(SRC + specifier.slice(2));
      if (file) return { url: pathToFileURL(file).href, shortCircuit: true };
    } else if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL?.startsWith("file:") && !/\.[cm]?[jt]sx?$/.test(specifier)) {
      const file = withTs(fileURLToPath(new URL(specifier, context.parentURL)));
      if (file) return { url: pathToFileURL(file).href, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});
