import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    // Recommandation typescript-eslint : vue-tsc vérifie déjà les identifiants inconnus.
    files: ['**/*.ts', '**/*.vue'],
    rules: { 'no-undef': 'off' },
  },
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      // False positives on <script setup> bindings that are only read from the template.
      'no-useless-assignment': 'off',
      // Formatting nitpicks better left to Prettier; not enforced in this project.
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
    },
  },
)
