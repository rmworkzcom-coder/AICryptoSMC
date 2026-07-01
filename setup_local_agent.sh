mkdir -p ~/.continue
cat << 'INNER_EOF' > ~/.continue/config.yaml
models:
  - title: "Gemma 4"
    provider: "ollama"
    model: "gemma4"
    roles:
      - chat
      - inlineEdit
      - autocomplete
