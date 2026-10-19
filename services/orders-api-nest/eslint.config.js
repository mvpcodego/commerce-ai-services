import js from "@eslint/js"
import globals from "globals"
import tseslint from "typescript-eslint"

export default tseslint.config(
  { ignores: ["dist/", "node_modules/", "coverage/"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.node, ...globals.jest },
      parserOptions: { projectService: { allowDefaultProject: ["*.js"] }, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      "@typescript-eslint/no-extraneous-class": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["test/**/*.ts", "src/**/*.spec.ts"],
    rules: {
      // supertest отдаёт body как any — в тестах это нормально
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-argument": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "@typescript-eslint/no-unsafe-return": "off",
      // фейки и обработчики в тестах повторяют асинхронный интерфейс без await внутри
      "@typescript-eslint/require-await": "off",
    },
  },
)
