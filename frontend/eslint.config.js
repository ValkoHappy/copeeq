import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["public/**", "src/templates/**"] },
  js.configs.recommended,
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
    },
  },
];
