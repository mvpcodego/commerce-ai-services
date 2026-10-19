import { base } from "./jest.config.js"

/** @type {import('jest').Config} */
export default { ...base, rootDir: ".", testRegex: "test/.*\\.e2e-spec\\.ts$", testTimeout: 30000 }
