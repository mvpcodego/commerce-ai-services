// Модули ESM (NestJS 12 — только ESM): Jest запускается с --experimental-vm-modules, ts-jest в режиме useESM.
/** @type {import('jest').Config} */
const base = {
  testEnvironment: "node",
  extensionsToTreatAsEsm: [".ts"],
  moduleNameMapper: { "^(\\.{1,2}/.*)\\.js$": "$1" },
  transform: { "^.+\\.ts$": ["ts-jest", { useESM: true, tsconfig: "tsconfig.json" }] },
}

export default { ...base, rootDir: "src", testRegex: ".*\\.spec\\.ts$" }
export { base }
