#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.local-llm"
COMPOSE=(-f "${ROOT_DIR}/docker-compose.llm.yml")

if [[ -f "${ROOT_DIR}/docker-compose.irene.yml" ]] && [[ "${PANDA_LLM_ENABLE_GPU:-1}" == "1" ]]; then
  COMPOSE+=(-f "${ROOT_DIR}/docker-compose.irene.yml")
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.local-llm.example and set a long random token." >&2
  exit 1
fi

dc() {
  docker compose --env-file "${ENV_FILE}" "${COMPOSE[@]}" "$@"
}

case "${1:-}" in
  up) dc up -d --build ;;
  down) dc down ;;
  status) dc ps ;;
  logs) dc logs --tail 200 "${2:-}" ;;
  test)
    dc exec -T gateway python -c \
      'import os,httpx; h={"Authorization":"Bearer "+os.environ["PANDA_INFERENCE_TOKEN"]}; u="http://127.0.0.1:8000"; print(httpx.get(u+"/health",timeout=10).json()); print(httpx.get(u+"/v1/models",headers=h,timeout=10).json()); print(httpx.post(u+"/v1/chat",headers=h,json={"model":os.environ.get("PANDA_ALLOWED_MODELS","qwen2.5:3b").split(",")[0],"messages":[{"role":"user","content":"Reply with PANDA model connected."}],"options":{"num_predict":24,"temperature":0}},timeout=180).json())'
    ;;
  *) echo "Usage: $0 {up|down|status|logs [service]|test}" >&2; exit 2 ;;
esac
